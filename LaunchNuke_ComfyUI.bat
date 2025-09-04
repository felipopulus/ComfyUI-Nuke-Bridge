@echo off
setlocal

rem ComfyUI-Nuke-Bridge: wrapper to launch Nuke with this plugin on NUKE_PATH

rem --- Configure paths -------------------------------------------------------
set "NUKE_EXE=C:\Program Files\Nuke16.0v5\Nuke16.0.exe"
rem Derive plugin dir from this script's location for portability
set "SCRIPT_DIR=%~dp0"
set "PLUGIN_DIR=%SCRIPT_DIR%"
rem If you prefer a fixed path, comment the 2 lines above and set PLUGIN_DIR explicitly
rem set "PLUGIN_DIR=C:\Users\felip\Desktop\ComfyUI-Nuke-Bridge"

if not exist "%NUKE_EXE%" (
  echo [ERROR] Nuke executable not found: "%NUKE_EXE%"
  echo Edit NUKE_EXE in this script if your Nuke path differs.
  pause
  exit /b 1
)

if not exist "%PLUGIN_DIR%\menu.py" (
  echo [ERROR] Plugin not found at: "%PLUGIN_DIR%"
  echo Edit PLUGIN_DIR in this script to point to your ComfyUI-Nuke-Bridge folder.
  pause
  exit /b 1
)

rem --- Add plugin to NUKE_PATH without losing existing value -----------------
if defined NUKE_PATH (
  set "NUKE_PATH=%PLUGIN_DIR%;%NUKE_PATH%"
) else (
  set "NUKE_PATH=%PLUGIN_DIR%"
)

rem --- Optional: set defaults for the plugin (can be overridden by env vars) --
if not defined NUKE_COMFYUI_DIR set "NUKE_COMFYUI_DIR=C:\Users\felip\Desktop\ComfyUI"
rem if not defined NUKE_COMFYUI_PYTHON set "NUKE_COMFYUI_PYTHON=C:\\Path\\To\\Python.exe"
rem if not defined NUKE_COMFYUI_IP set "NUKE_COMFYUI_IP=127.0.0.1"
rem if not defined NUKE_COMFYUI_PORT set "NUKE_COMFYUI_PORT=8188"
rem if not defined NUKE_COMFYUI_FLAGS set "NUKE_COMFYUI_FLAGS=--log-stdout --disable-auto-launch"

rem --- Info ------------------------------------------------------------------
echo [INFO] NUKE_PATH=%NUKE_PATH%
echo [INFO] NUKE_COMFYUI_DIR=%NUKE_COMFYUI_DIR%

rem --- Launch Nuke with --nc and pass through any extra args ------------------
echo [INFO] Launching Nuke...
"%NUKE_EXE%" --nc %*

endlocal
