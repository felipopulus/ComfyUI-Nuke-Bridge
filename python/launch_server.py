"""
ComfyUI-Nuke-Bridge (Lite) - server launcher

MVP responsibilities:
- Start a local ComfyUI server in a non-blocking subprocess
- Capture server stdout/stderr
- Parse and print the local URL to Nuke's script editor

Notes:
- For now, we hardcode the ComfyUI path via environment var or a default.
- Future: make discovery dynamic (scan common locations / project env vars).
"""
from __future__ import annotations
import os
import sys
import shlex
import threading
import subprocess
import time
import re
import atexit
from typing import Optional

try:
    import nuke  # type: ignore
except Exception:  # pragma: no cover
    # Allow import outside Nuke for basic unit testing/logging
    class _Stub:
        @staticmethod
        def tprint(msg: str):
            print(msg)
    nuke = _Stub()  # type: ignore


# --- Configuration ---------------------------------------------------------
# Hardcoded-ish defaults with env overrides. Adjust as needed.
# Required: Path to your local ComfyUI checkout (folder that has main.py).
COMFYUI_DIR = os.environ.get(
    "NUKE_COMFYUI_DIR",
    r"C:\\Users\\felip\\Desktop\\ComfyUI"  # TODO: make dynamic later
)
# Optional: Which python to use to run ComfyUI. Preference order:
# 1) NUKE_COMFYUI_PYTHON env var (explicit override)
# 2) Python inside ComfyUI's own venv (COMFYUI_DIR/.venv)
# 3) Current interpreter (sys.executable)
_env_override = os.environ.get("NUKE_COMFYUI_PYTHON")
if _env_override:
    COMFYUI_PYTHON = _env_override
else:
    if os.name == "nt":
        _venv_py = os.path.join(COMFYUI_DIR, ".venv", "Scripts", "python.exe")
    else:
        _venv_py = os.path.join(COMFYUI_DIR, ".venv", "bin", "python")
    COMFYUI_PYTHON = _venv_py if os.path.isfile(_venv_py) else sys.executable
# Bind IP/Port
COMFYUI_IP = os.environ.get("NUKE_COMFYUI_IP", "127.0.0.1")
COMFYUI_PORT = int(os.environ.get("NUKE_COMFYUI_PORT", "8188"))
# Additional flags for ComfyUI (keep minimal for MVP)
COMFYUI_FLAGS = os.environ.get("NUKE_COMFYUI_FLAGS", "--log-stdout --disable-auto-launch")

# Regex to catch the server URL, supports IPv4/IPv6, requires an explicit port
# Examples matched:
#   http://127.0.0.1:8188
#   https://localhost:443
#   http://[::1]:8188
URL_WITH_PORT_REGEX = re.compile(r"(https?://(?:\[[^\]]+\]|[^/\s:]+):\d+)")

# --- Process management ----------------------------------------------------
_process: Optional[subprocess.Popen] = None
_reader_thread: Optional[threading.Thread] = None

# Status signaling for UI
_status_cb = None  # type: Optional[callable]
_status_lock = threading.Lock()
_status_event = threading.Event()
_last_status: str = "idle"


def set_status_callback(cb):
    """Register a callback(status: str) invoked on status changes.
    Status values: 'idle', 'launching', 'already_running', 'running', 'error', 'stopped'.
    """
    global _status_cb
    with _status_lock:
        _status_cb = cb


def _set_status(status: str):
    global _last_status
    with _status_lock:
        _last_status = status
        _status_event.set()
        _status_event.clear()
        cb = _status_cb
    try:
        if cb:
            cb(status)
    except Exception as _e:  # pragma: no cover
        # Avoid crashing if UI callback has issues
        nuke.tprint(f"[ComfyUI] Status callback error: {_e}")


def wait_until_ready(timeout: float = 30.0) -> str:
    """Wait until a terminal state: running, already_running, or error.
    Returns the last status when exiting (or the latest observed before timeout).
    """
    terminal = {"running", "already_running", "error"}
    end_time = time.time() + timeout
    while time.time() < end_time:
        with _status_lock:
            status = _last_status
        if status in terminal:
            return status
        # Also consider if process died early
        if _process and _process.poll() is not None:
            _set_status("error")
            return "error"
        _status_event.wait(0.2)
    return status


def _build_command() -> list[str]:
    """Build the command list to start ComfyUI."""
    main_py = os.path.join(COMFYUI_DIR, "main.py")
    server_py = os.path.join(COMFYUI_DIR, "server.py")

    entry = main_py if os.path.isfile(main_py) else server_py
    if not os.path.isfile(entry):
        raise RuntimeError(
            f"ComfyUI entry script not found. Checked: {main_py} and {server_py}. "
            f"Configure NUKE_COMFYUI_DIR correctly. Current: {COMFYUI_DIR}"
        )

    cmd = [
        COMFYUI_PYTHON,
        "-u",  # unbuffered stdout/stderr from child python
        entry,
        "--listen", str(COMFYUI_IP),
        "--port", str(COMFYUI_PORT),
    ]

    if COMFYUI_FLAGS:
        # Use shlex to split user-supplied flags safely
        cmd.extend(shlex.split(COMFYUI_FLAGS))

    return cmd


def _reader_loop(pipe, name: str):
    """Continuously read process output and print to Nuke, extract URL."""
    url_reported = False
    for line in iter(pipe.readline, ""):
        line = line.rstrip()

        # Send line to Nuke script editor
        nuke.tprint(f"[ComfyUI:{name}] {line}")

        if not url_reported:
            m = URL_WITH_PORT_REGEX.search(line)
            if m:
                url = m.group(0)
                nuke.tprint(f"[ComfyUI] Server running at: {url}")
                url_reported = True
                _set_status("running")

    pipe.close()
    # If we had launched and the pipe closed, mark as stopped unless we already errored
    with _status_lock:
        current = _last_status
    if current not in {"error", "already_running"}:
        _set_status("stopped")


def launch_comfyui_server():
    """Launch ComfyUI server in a background subprocess.

    - Non-blocking
    - Streams stdout/stderr into Nuke's script editor
    - Prints the URL when available
    """
    global _process, _reader_thread

    if _process and _process.poll() is None:
        nuke.tprint("[ComfyUI] Server already running.")
        _set_status("already_running")
        return

    try:
        cmd = _build_command()
    except Exception as e:
        nuke.tprint(f"[ComfyUI] Failed to build command: {e}")
        _set_status("error")
        return

    nuke.tprint(f"[ComfyUI] Using Python: {COMFYUI_PYTHON}")
    nuke.tprint("[ComfyUI] Launching: {}".format(" ".join(shlex.quote(c) for c in cmd)))
    _set_status("launching")

    # Ensure working directory is ComfyUI root (so relative paths work)
    cwd = COMFYUI_DIR

    # Avoid opening a console window on Windows
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        _process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,  # line-buffered when text=True
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except FileNotFoundError as e:
        nuke.tprint(f"[ComfyUI] Failed to launch (python not found?): {e}")
        _set_status("error")
        return
    except Exception as e:
        nuke.tprint(f"[ComfyUI] Failed to launch: {e}")
        _set_status("error")
        return

    # Start reader thread to stream logs
    assert _process.stdout is not None
    _reader_thread = threading.Thread(target=_reader_loop, args=(_process.stdout, "stdout"), daemon=True)
    _reader_thread.start()

    # Optional: brief wait to surface early errors
    time.sleep(0.2)
    if _process.poll() is not None:
        nuke.tprint(f"[ComfyUI] Server exited immediately with code: {_process.returncode}")
        _process = None
        _set_status("error")
        return

    nuke.tprint("[ComfyUI] Server process started (PID: {}). Waiting for URL...".format(_process.pid))


def stop_comfyui_server(timeout: float = 5.0):
    """Stop the ComfyUI subprocess if running.
    Attempts graceful terminate, then kill if needed.
    """
    global _process
    proc = _process
    if not proc or proc.poll() is not None:
        _process = None
        _set_status("stopped")
        return
    try:
        nuke.tprint(f"[ComfyUI] Stopping server (PID: {proc.pid}) ...")
        proc.terminate()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        if proc.poll() is None:
            nuke.tprint("[ComfyUI] Force-killing server ...")
            proc.kill()
    except Exception as e:
        nuke.tprint(f"[ComfyUI] Error while stopping server: {e}")
    finally:
        _process = None
        _set_status("stopped")


def _atexit_cleanup():  # pragma: no cover
    try:
        stop_comfyui_server()
    except Exception:
        pass


# Ensure cleanup on interpreter shutdown (e.g., when Nuke exits)
atexit.register(_atexit_cleanup)
