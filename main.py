from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import asyncio
import os
import signal
from scraper import get_listening_connections

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: list):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)
        
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

async def scan_loop():
    while True:
        if manager.active_connections: 
            connections = get_listening_connections()
            await manager.broadcast(connections)
        await asyncio.sleep(0.5)

@app.on_event("startup")
async def start_background_scanner():
    asyncio.create_task(scan_loop())

@app.websocket("/ws/scan")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected")

@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    if pid <= 1000:
        raise HTTPException(status_code=403, detail="Cannot kill critical system processes.")
    try:
        os.kill(pid, signal.SIGKILL)
        return {"message": f"Process {pid} killed successfully."}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail=f"Process with PID {pid} not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied to kill process {pid}.")
    except Exception as e:
        print(f"An error occurred: {e}")


@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    if pid <= 1000:  # Basic safety check for system processes
        raise HTTPException(status_code=403, detail="Cannot kill critical system processes.")
    
    try:
        os.kill(pid, signal.SIGKILL)
        return {"message": f"Process {pid} killed successfully."}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail=f"Process with PID {pid} not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied to kill process {pid}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))