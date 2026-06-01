from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from scraper import get_listening_connections

app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    previous_connections = set()
    try:
        while True:
            current_connections_list = get_listening_connections()
            current_connections = set(tuple(sorted(d.items())) for d in current_connections_list)

            if current_connections != previous_connections:
                await websocket.send_json(current_connections_list)
                previous_connections = current_connections
            
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"An error occurred: {e}")