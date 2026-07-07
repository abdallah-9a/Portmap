# src/portmap/cli.py
import argparse
import uvicorn
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="portmap",
        description="Real-time dashboard for local listening ports."
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=7474,
        help="Port to run the Portmap dashboard on (default: 7474)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 1.1.0"
    )
    args = parser.parse_args()

    print(f"Portmap running at http://{args.host}:{args.port}")
    uvicorn.run(
        "portmap.main:app",
        host=args.host,
        port=args.port,
        log_level="warning"   # suppress uvicorn noise, portmap speaks for itself
    )


if __name__ == "__main__":
    main()
