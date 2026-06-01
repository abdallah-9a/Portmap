import psutil
KNOWN_SIGNATURES = {
    "uvicorn": {"name": "FastAPI", "color": "bg-teal-500"},
    "django": {"name": "Django", "color": "bg-green-600"},
    ".vscode": {"name": "VS Code Service", "color": "bg-purple-600"},
    "docker-proxy": {"name": "Docker", "color": "bg-blue-600"},
    "node": {"name": "Node.js", "color": "bg-yellow-500"},
    "redis-server": {"name": "Redis", "color": "bg-red-500"},
    "postgres": {"name": "PostgreSQL", "color": "bg-blue-500"}
}
def get_listening_connections():
    connections_list = []

    for conn in psutil.net_connections(kind='inet'):
        if conn.status == 'LISTEN':
            port = conn.laddr.port
            pid = conn.pid

            app_name = "Unknown"
            badge_color = "bg-slate-500"

            if pid is not None:
                try:
                    process = psutil.Process(pid)
                    raw_name = process.name()
                    try:
                        cmdline = " ".join(process.cmdline()).lower()
                    except (psutil.AccessDenied, psutil.ZombieProcess):
                        cmdline = ""

                    found = False
                    for key, meta in KNOWN_SIGNATURES.items():
                        if key in cmdline or key in raw_name.lower():
                            app_name = meta["name"]
                            badge_color = meta["color"]
                            found = True
                            break

                    if not found:
                        app_name = raw_name
                        badge_color = "bg-blue-500"

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    app_name = "Protected"
                    badge_color = "bg-slate-700"
            else:
                app_name = "Protected"
                badge_color = "bg-slate-700"

            connection_info = {
                "port": port,
                "pid": pid,
                "name": app_name,
                "color": badge_color
            }
            connections_list.append(connection_info)

    connections_list.sort(key=lambda x: x["port"])
    return connections_list