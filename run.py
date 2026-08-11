import argparse
import logging
import os
import socket
import sys

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def port_in_use(host: str, port: int) -> bool:
    """True if something is already accepting connections on host:port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
    except OSError:
        return False
    return False


def find_pid_on_port(port: int):
    """Best-effort: return the PID of the process LISTENING on the port."""
    try:
        out = os.popen(f'netstat -ano | findstr ":{port}" | findstr "LISTENING"').read()
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[4].isdigit():
                return parts[4]
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="HaloVision backend server")
    parser.add_argument("--host", default=os.getenv("HOST", HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", PORT)))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("run")

    # Refuse to start before importing App.main, so a duplicate instance fails
    # fast without loading torch/MiDaS/YOLO.
    if port_in_use(args.host, args.port):
        pid = find_pid_on_port(args.port)
        owner = f"PID {pid}" if pid else "another process"
        logger.error(
            "Port %s:%s is already in use by %s - HaloVision is probably already running.",
            args.host,
            args.port,
            owner,
        )
        logger.error(
            "Stop the running instance (taskkill /F /PID %s) or run this one on a "
            "free port: python run.py --port <free-port>.",
            pid or "<pid>",
        )
        sys.exit(2)

    logger.info("Starting HaloVision server on http://%s:%s", args.host, args.port)
    uvicorn.run("App.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
