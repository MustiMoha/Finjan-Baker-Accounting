#!/usr/bin/env python3
"""Start Ali Al Baker Accounting Dashboard: auth UI + API + Streamlit with one command."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUTH_WEB = ROOT / "auth_web"
DIST = AUTH_WEB / "dist" / "index.html"

API_HOST = "127.0.0.1"
API_PORT = 8000
STREAMLIT_HOST = "127.0.0.1"
STREAMLIT_PORT = 8501
STREAMLIT_PUBLIC_URL = f"http://{STREAMLIT_HOST}:{STREAMLIT_PORT}"


def _npm() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _shell() -> bool:
    return sys.platform == "win32"


def _needs_rebuild() -> bool:
    if not DIST.is_file():
        return True
    dist_mtime = DIST.stat().st_mtime
    src = AUTH_WEB / "src"
    if not src.is_dir():
        return False
    for path in src.rglob("*"):
        if path.is_file() and path.stat().st_mtime > dist_mtime:
            return True
    return False


def ensure_frontend(*, force: bool = False) -> None:
    if DIST.is_file() and not force and not _needs_rebuild():
        return
    if not shutil.which("npm") and not (sys.platform == "win32" and shutil.which("npm.cmd")):
        sys.exit("Node.js/npm is required to build the auth UI. Install from https://nodejs.org/")
    if not (AUTH_WEB / "node_modules").is_dir():
        print("Installing auth UI dependencies…")
        subprocess.run([_npm(), "install"], cwd=AUTH_WEB, check=True, shell=_shell())
    print("Building auth UI…")
    subprocess.run([_npm(), "run", "build"], cwd=AUTH_WEB, check=True, shell=_shell())


def _pids_listening_on(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
            needle = f":{port}"
            for line in out.splitlines():
                if needle not in line or "LISTENING" not in line.upper():
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
        else:
            out = subprocess.check_output(["lsof", "-ti", f"tcp:{port}"], text=True, stderr=subprocess.DEVNULL)
            for tok in out.split():
                if tok.isdigit():
                    pids.add(int(tok))
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return pids


def free_port(port: int, *, label: str) -> None:
    """Release a TCP listen port so Baker can bind predictably."""
    own_pid = os.getpid()

    for pid in _pids_listening_on(port):
        if pid <= 0 or pid == own_pid:
            continue
        print(f"Stopping process {pid} on port {port} ({label})…")
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(["kill", "-9", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if _pids_listening_on(port):
        sys.exit(f"Port {port} ({label}) is still in use. Close the other app and retry.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Ali Al Baker Accounting Dashboard")
    parser.add_argument("--build", action="store_true", help="Force rebuild of the auth UI")
    parser.add_argument("--no-build", action="store_true", help="Skip auth UI build (use existing dist/)")
    args = parser.parse_args()

    if not args.no_build:
        ensure_frontend(force=args.build)

    procs: list[subprocess.Popen[bytes]] = []

    def shutdown(*_args: object) -> None:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    print("Starting Ali Al Baker Accounting Dashboard…")
    free_port(API_PORT, label="API")
    free_port(STREAMLIT_PORT, label="Financials")

    procs.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                API_HOST,
                "--port",
                str(API_PORT),
            ],
            cwd=ROOT,
        )
    )
    time.sleep(0.8)

    procs.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.headless",
                "true",
                "--server.address",
                STREAMLIT_HOST,
                "--server.port",
                str(STREAMLIT_PORT),
            ],
            cwd=ROOT,
        )
    )

    print()
    print(f"  App:         http://{API_HOST}:{API_PORT}")
    print(f"  Dashboard:   http://{API_HOST}:{API_PORT}/dashboard")
    print(f"  Financials:  {STREAMLIT_PUBLIC_URL}  (Streamlit — linked from sidebar)")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        while True:
            for proc in procs:
                if proc.poll() is not None:
                    shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
