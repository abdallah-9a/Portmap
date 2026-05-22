from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import asyncio
import os
import signal
from scraper import get_listening_connections

app = FastAPI()


@app.websocket("/ws/scan")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            connections = get_listening_connections()
            await websocket.send_json(connections)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        print("Client disconnected")
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