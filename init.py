"""
ComfyUI-Nuke-Bridge (Lite) - init hook

Executed by Nuke at startup. It ensures the plugin's Python modules are
importable by adding this package's `python/` directory to sys.path.

You can optionally set environment variables to configure the server launch:
- NUKE_COMFYUI_DIR: Absolute path to your local ComfyUI checkout
- NUKE_COMFYUI_PYTHON: Path to a Python 3.10+ executable with ComfyUI deps
- NUKE_COMFYUI_IP: IP address to bind (default: 127.0.0.1)
- NUKE_COMFYUI_PORT: Port to bind (default: 8188)
"""
from __future__ import annotations
import os
import sys
import traceback

# Ensure `python/` is on sys.path for imports like `import launch_server`
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PY_DIR = os.path.join(_THIS_DIR, "python")
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

# Ensure project's venv site-packages are importable inside Nuke
_VENV_DIR = os.path.join(_THIS_DIR, ".venv")
_VENV_SITE = os.path.join(_VENV_DIR, "Lib", "site-packages")  # Windows venv layout
try:
    if os.path.isdir(_VENV_SITE) and _VENV_SITE not in sys.path:
        sys.path.insert(0, _VENV_SITE)
        # Optional: uncomment for debugging
        # import nuke  # type: ignore
        # nuke.tprint(f"[ComfyUi] Added venv site-packages to sys.path: {_VENV_SITE}")
except Exception:
    # Don't break Nuke startup if venv isn't present
    pass

# Register shutdown hook to ensure ComfyUI subprocess is stopped when Nuke exits
try:
    import nuke  # type: ignore
    try:
        from launch_server import stop_comfyui_server  # type: ignore
        nuke.addOnDestroy(stop_comfyui_server)
    except Exception:
        # Log but do not fail startup
        try:
            nuke.tprint("[ComfyUiLite] Could not register shutdown hook:\n" + traceback.format_exc())
        except Exception:
            pass
except Exception:
    # Outside of Nuke or nuke module unavailable
    pass
