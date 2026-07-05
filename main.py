from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from scraper import get_listening_connections
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import asyncio
import psutil

# UIDs below this are reserved for privileged/system accounts on Linux
# (root is 0; the 1..999 range is daemons and service users). Ownership —
# not the PID value — is what determines whether a process is safe to kill.
SYSTEM_UID_MAX = 1000

# Hostnames that count as "the local machine". A request's Origin is only
# trusted when it points at one of these on the same port the request was
# sent to — see is_allowed_origin().
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def is_allowed_origin(origin: str | None, host: str | None) -> bool:
    """Decide whether a browser Origin may talk to Portmap.

    Portmap binds to localhost, but that does not stop another site open in
    the same browser from calling our endpoints — the browser sends those
    requests from the user's machine. The defense is the Origin header, which
    the browser sets to the calling page's origin and which a page cannot
    forge.

    Policy:
      * No Origin header  → allow. Browsers always attach Origin to the
        cross-site WebSocket and POST requests we care about, so a missing
        Origin means a non-browser client (curl, tests), not the threat model.
      * Origin present     → its host must be loopback AND its port must match
        the port this request was sent to (the Host header). This transparently
        accepts whatever address the user opened the UI on (127.0.0.1 or
        localhost, any port) while rejecting every external site.
    """
    if origin is None:
        return True

    parsed = urlparse(origin)
    if parsed.hostname is None or parsed.hostname.lower() not in LOOPBACK_HOSTS:
        return False

    # The Origin's port must match the port the request was actually sent to,
    # so a page served from a *different* local port cannot reach us either.
    host_port = None
    if host:
        host_port = host.rsplit(":", 1)[-1] if ":" in host else None

    return _port_of(parsed) == host_port


def _port_of(parsed) -> str | None:
    if parsed.port is not None:
        return str(parsed.port)
    # No explicit port → the scheme's default (http → 80, https → 443).
    return {"http": "80", "https": "443"}.get(parsed.scheme)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background scanner and keep a handle so we can stop it cleanly.
    scanner = asyncio.create_task(scan_loop())
    try:
        yield
    finally:
        scanner.cancel()
        try:
            await scanner
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)
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
    # Reject cross-site sockets before the handshake completes. A page from
    # another origin can open a WebSocket to us, so the Origin must be checked
    # here just as it is on the kill endpoint.
    if not is_allowed_origin(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=1008)  # 1008 = policy violation
        return

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
async def kill_process(pid: int, request: Request):
    # Block cross-site kill requests. Any page in the user's browser can POST
    # here; only requests originating from the Portmap UI itself are allowed.
    if not is_allowed_origin(
        request.headers.get("origin"), request.headers.get("host")
    ):
        raise HTTPException(status_code=403, detail="Origin not allowed.")

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