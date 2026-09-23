# =============================================================================
# FILE: run.py
# ROLE: Application entry point — the script you execute to start the server.
#
# WHAT THIS FILE DOES:
#   1. Parses command-line arguments (host, port)
#   2. Checks if the port is already in use (prevents duplicate instances)
#   3. Launches the FastAPI application via Uvicorn ASGI server
#
# FLOW:
#   python run.py
#       ↓
#   port_in_use() check → refuse to start if already running
#       ↓
#   uvicorn.run("App.main:app") → starts ASGI server
#       ↓
#   FastAPI app (App/main.py) boots → database migrations → AI system init
#       ↓
#   Server listening on http://127.0.0.1:8000
# =============================================================================

import argparse
import logging
import os
import socket
import sys

import uvicorn

# Default server binding — can be overridden via CLI args or .env
HOST = "127.0.0.1"
PORT = 8000


def port_in_use(host: str, port: int) -> bool:
    """Check if a port is already occupied.
    This prevents launching a second HaloVision instance which would
    cause port conflicts and load duplicate ML models into memory."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
    except OSError:
        return False
    return False


def find_pid_on_port(port: int):
    """Find the process ID (PID) that owns a given port.
    Used to give the user a helpful error message telling them
    which process to kill if the port is taken."""
    try:
        # Windows-specific: uses netstat to find the process listening on the port
        out = os.popen(f'netstat -ano | findstr ":{port}" | findstr "LISTENING"').read()
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[4].isdigit():
                return parts[4]
    except Exception:
        pass
    return None


def main():
    # --- Step 1: Parse CLI arguments ---
    parser = argparse.ArgumentParser(description="HaloVision backend server")
    parser.add_argument("--host", default=os.getenv("HOST", HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", PORT)))
    args = parser.parse_args()

    # --- Step 2: Set up logging ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("run")

    # --- Step 3: Port conflict check ---
    # Do this BEFORE importing App.main to fail fast without loading
    # heavy ML models (torch, YOLO, MiDaS) into memory.
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

    # --- Step 4: Launch the ASGI server ---
    # "App.main:app" is a string reference — Uvicorn imports it lazily.
    # This triggers FastAPI app creation, database init, ML model loading,
    # and the startup event that wires up the entire AI pipeline.
    logger.info("Starting HaloVision server on http://%s:%s", args.host, args.port)
    uvicorn.run("App.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
