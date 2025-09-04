# ComfyUI-Nuke-Bridge
Minimal Nuke plugin to launch a local ComfyUI server from Nuke and print the server URL to the Script Editor.

## What it does (MVP)
- Adds a top-level `ComfyUI` menu in Nuke.
- Provides a `Launch Local Server` command.
- Starts ComfyUI in a background subprocess and streams logs into Nuke.
- Parses the URL (e.g. `http://127.0.0.1:8188`) and prints it in Nuke.

## Install
Option A: copy this folder into your Nuke user folder so Nuke auto-loads `init.py` and `menu.py`:
- Windows: `%USERPROFILE%\\.nuke\\ComfyUI-Nuke-Bridge`
- Linux/macOS: `~/.nuke/ComfyUI-Nuke-Bridge`

Option B: add the plugin path in your `~/.nuke/menu.py`:
```python
import nuke, os
nuke.pluginAddPath(r"C:/path/to/ComfyUI-Nuke-Bridge")
```

## Configuration (env vars)
You can override defaults with environment variables before launching Nuke:
- `NUKE_COMFYUI_DIR` (required if not at default): absolute path to your ComfyUI checkout. Default: `C:\Users\<you>\Desktop\ComfyUI`.
- `NUKE_COMFYUI_PYTHON` (optional): path to a Python 3.10+ executable with ComfyUI deps. Default: Nuke's Python.
- `NUKE_COMFYUI_IP`: bind IP (default `127.0.0.1`).
- `NUKE_COMFYUI_PORT`: port (default `8188`).
- `NUKE_COMFYUI_FLAGS`: extra CLI flags (default `--log-stdout --disable-auto-launch`).

Examples (Windows PowerShell) before starting Nuke:
```powershell
$env:NUKE_COMFYUI_DIR = 'C:\\Users\\<you>\\Desktop\\ComfyUI'
# Optional: use a specific Python
# $env:NUKE_COMFYUI_PYTHON = 'C:\\Program Files\\Python311\\python.exe'
```

## Usage
1) Start Nuke.
2) Click `ComfyUI > Launch Local Server`.
3) Watch the Script Editor. When ready, you'll see:
```
[ComfyUI] Server running at: http://127.0.0.1:8188
```
4) Open that URL in a browser.

## Notes
- The launcher looks for `main.py` (preferred) or `server.py` in `NUKE_COMFYUI_DIR`.
- Logs are streamed with `-u` (unbuffered) and hidden console window on Windows.
- The browser auto-open is disabled by default to avoid stealing focus from Nuke.
