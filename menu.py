"""
ComfyUI-Nuke-Bridge (Lite) - menu hook

Creates a top-level "ComfyUI" menu in Nuke with a single command to
launch a local ComfyUI server in the background and report its URL.
"""
from __future__ import annotations
import nuke  # type: ignore

# Import from our python/ folder (init.py adds it to sys.path)
try:
    from launch_server import launch_comfyui_server
except Exception as e:  # pragma: no cover
    nuke.tprint("[ComfyUI] Failed to import launch_server: {}".format(e))
    raise


# Build main menu in Nuke's top bar
_comfy_menu = nuke.menu('Nuke').addMenu('ComfyUI')

# Add commands
_comfy_menu.addCommand(
    'Launch Local Server',
    launch_comfyui_server,
)
