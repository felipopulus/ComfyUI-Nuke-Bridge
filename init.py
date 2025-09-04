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

# Ensure `python/` is on sys.path for imports like `import launch_server`
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PY_DIR = os.path.join(_THIS_DIR, "python")
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)
