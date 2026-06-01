from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from scraper import get_listening_connections
import asyncio
import os
import signal

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()
_previous_snapshot: list = []


@app.on_event("startup")
async def start_scanner():
    asyncio.create_task(scan_loop())

async def scan_loop():
    global _previous_snapshot
    while True:
        try:
            current = get_listening_connections()

            if current != _previous_snapshot:
                await manager.broadcast(current)
                _previous_snapshot = current
        except Exception as e:
            print(f"Scanner error: {e}")
        await asyncio.sleep(0.5)


@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

@app.websocket("/ws/scan")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)

    if _previous_snapshot:
        await ws.send_json(_previous_snapshot)
    try:
        while True:
            await ws.receive_text()  
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)

@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    if pid <= 1000:
        raise HTTPException(status_code=403, detail="Cannot kill system processes.")
    try:
        os.kill(pid, signal.SIGKILL)
        return {"message": f"Process {pid} killed successfully."}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail=f"PID {pid} not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied for PID {pid}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))