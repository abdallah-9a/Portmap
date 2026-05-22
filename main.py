from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
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