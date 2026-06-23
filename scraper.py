import psutil
from pathlib import Path

FRAMEWORK_MARKERS = {
    "manage.py":        "Django",
    "pyproject.toml":   "Python",
    "requirements.txt": "Python",
    "package.json":     "Node.js",
    "go.mod":           "Go",
    "Cargo.toml":       "Rust",
    "Gemfile":          "Ruby",
    "pom.xml":          "Java",
    "composer.json":    "PHP",
}

INFRASTRUCTURE = {
    "redis-server": "Redis",
    "postgres":     "PostgreSQL",
    "mysqld":       "MySQL",
    "mongod":       "MongoDB",
    "nginx":        "Nginx",
    "docker-proxy": "Docker",
}

SKIP_PROCESSES = {
    "code", "code-oss", "codium", "cursor",
    "webstorm", "idea", "pycharm", "clion", "rider",
    "postman", "insomnia",
}

SKIP_FLAGS = {
    "--type=renderer", "--type=gpu-process",
    "--type=utility",  "--type=broker",
    "node.mojom.nodeservice",
}


def _should_skip(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        name = proc.name().lower().removesuffix(".exe")
        if name in SKIP_PROCESSES:
            return True
        cmdline = " ".join(proc.cmdline())
        return any(flag in cmdline for flag in SKIP_FLAGS)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return True


def _find_git_root(pid: int) -> Path | None:
    try:
        path = Path(psutil.Process(pid).cwd())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None

    for _ in range(6):
        if (path / ".git").exists():
            return path
        parent = path.parent
        if parent == path:
            break
        path = parent
    return None


def _project_name(git_root: Path) -> str:
    # The git root directory name is the project name 
    return git_root.name or str(git_root)


def _identify_framework(git_root: Path) -> str:
    try:
        entries = {e.name for e in git_root.iterdir()}
    except OSError:
        return "Project"
    for marker, framework in FRAMEWORK_MARKERS.items():
        if marker in entries:
            return framework
    return "Project"


def get_listening_connections() -> list[dict]:
    results = []
    seen = set()

    for conn in psutil.net_connections(kind='inet'):
        if conn.status != 'LISTEN':
            continue

        port, pid = conn.laddr.port, conn.pid
        if (port, pid) in seen:
            continue
        seen.add((port, pid))

        # No PID → kernel/system
        if pid is None:
            results.append({"port": port, "pid": None,
                            "name": "System", "framework": None,
                            "cwd": None, "kind": "system"})
            continue

        # Skip IDE workers and Chromium internal processes
        if _should_skip(pid):
            continue

        # Git root → confirmed project
        git_root = _find_git_root(pid)
        if git_root:
            framework = _identify_framework(git_root)
            project = _project_name(git_root)
            results.append({"port": port, "pid": pid,
                            "name": project, "framework": framework,
                            "cwd": str(git_root), "kind": "project"})
            continue

        # Known infrastructure daemon
        raw_name = psutil.Process(pid).name() if pid else "unknown"
        if raw_name.lower() in INFRASTRUCTURE:
            label = INFRASTRUCTURE[raw_name.lower()]
            results.append({"port": port, "pid": pid,
                            "name": label, "framework": label,
                            "cwd": None, "kind": "infrastructure"})
            continue

        # Honest fallback
        results.append({"port": port, "pid": pid,
                        "name": raw_name, "framework": None,
                        "cwd": None, "kind": "unknown"})

    results.sort(key=lambda x: x["port"])
    return results