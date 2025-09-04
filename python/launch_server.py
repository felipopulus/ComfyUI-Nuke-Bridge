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
# Optional: Which python to use to run ComfyUI. If empty, use current python.
COMFYUI_PYTHON = os.environ.get("NUKE_COMFYUI_PYTHON", sys.executable)
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

    pipe.close()


def launch_comfyui_server():
    """Launch ComfyUI server in a background subprocess.

    - Non-blocking
    - Streams stdout/stderr into Nuke's script editor
    - Prints the URL when available
    """
    global _process, _reader_thread

    if _process and _process.poll() is None:
        nuke.tprint("[ComfyUI] Server already running.")
        return

    try:
        cmd = _build_command()
    except Exception as e:
        nuke.tprint(f"[ComfyUI] Failed to build command: {e}")
        return

    nuke.tprint("[ComfyUI] Launching: {}".format(" ".join(shlex.quote(c) for c in cmd)))

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
        return
    except Exception as e:
        nuke.tprint(f"[ComfyUI] Failed to launch: {e}")
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
        return

    nuke.tprint("[ComfyUI] Server process started (PID: {}). Waiting for URL...".format(_process.pid))
