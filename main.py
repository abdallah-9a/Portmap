from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from scraper import get_listening_connections
import asyncio
import psutil

# UIDs below this are reserved for privileged/system accounts on Linux
# (root is 0; the 1..999 range is daemons and service users). Ownership —
# not the PID value — is what determines whether a process is safe to kill.
SYSTEM_UID_MAX = 1000

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
            # psutil scanning is blocking (net_connections + per-PID /proc and
            # filesystem reads). Run it in a worker thread so the event loop
            # stays responsive for websocket broadcasts and the kill endpoint.
            current = await asyncio.to_thread(get_listening_connections)

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
    try:
        proc = psutil.Process(pid)
        owner_uid = proc.uids().real
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"PID {pid} not found.")
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail=f"Permission denied for PID {pid}.")

    # Protect processes owned by privileged/system accounts, regardless of PID.
    if owner_uid < SYSTEM_UID_MAX:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot kill process {pid}: owned by a protected system account.",
        )

    try:
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, timeout=5)
            return {
                "message": f"Process {pid} terminated gracefully.",
                "method": "SIGTERM"
            }
        except psutil.TimeoutExpired:
            proc.kill()
            await asyncio.to_thread(proc.wait, timeout=2)
            return {
                "message": f"Process {pid} force killed after graceful termination timeout.",
                "method": "SIGKILL"
            }
    except psutil.NoSuchProcess:
        return {
            "message": f"Process {pid} terminated.",
            "method": "SIGTERM"
        }
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail=f"Permission denied for PID {pid}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))