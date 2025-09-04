"""
ComfyUI-Nuke-Bridge (Lite) - menu hook

Creates a top-level "ComfyUI" menu in Nuke with a single menu item that
updates in place to reflect server status and toggles start/stop behavior.
"""
from __future__ import annotations
import nuke  # type: ignore
import threading

"""Menu setup and status wiring for ComfyUi."""

# Import from our python/ folder (init.py adds it to sys.path)
try:
    from launch_server import (
        launch_comfyui_server,
        set_status_callback,
        wait_until_ready,
        stop_comfyui_server,
    )
except Exception as e:  # pragma: no cover
    nuke.tprint("[ComfyUiLite] Failed to import launch_server: {}".format(e))
    raise


# Build main menu in Nuke's top bar
_comfy_menu = nuke.menu('Nuke').addMenu('ComfyUi')

# Internal: single toggle menu item and status tracking ----------------------------
_CURRENT_STATUS = "idle"
_MENU_ITEM_LABEL = "Start ComfyUI Server (Status: ⚪idle)"
_MENU_ITEM_OBJ = None  # type: ignore
_MENU_ITEM_NAME = None  # type: ignore
_MENU_PLACEHOLDER = "__ComfyUi_Toggle__"

def _get_menu():
    """Get or create the top-level ComfyUi menu safely.

    Returns the menu object or None on failure (without raising).
    """
    global _comfy_menu
    try:
        # Re-acquire each time in case Nuke hid the menu when empty
        root = nuke.menu('Nuke')
        _comfy_menu = root.addMenu('ComfyUi')
        return _comfy_menu
    except Exception as e:
        try:
            nuke.tprint(f"[ComfyUi] Could not get/create ComfyUi menu: {e}")
        except Exception:
            pass
        return None

def _cleanup_legacy_menu_items():
    """Remove any previously created menu entries to avoid duplicates.

    This covers legacy labels from earlier implementations and our placeholder.
    Safe to call multiple times.
    """
    menu = _get_menu()
    if not menu:
        return
    candidates = [
        _MENU_PLACEHOLDER,
        "Launch Local Server",
        "Stop Server",
        "Start ComfyUI Server (Status: ⚪idle)",
        "Status:🔵starting server...",
        "Start ComfyUI Server (Status: 🔴error)",
        "Start ComfyUI Server (Status: 🛑stopped)",
        "Stop ComfyUI server  (Status: 🟢running)",
    ]
    for name in candidates:
        try:
            menu.removeItem(name)  # type: ignore[attr-defined]
        except Exception:
            pass


def _status_emoji(status: str) -> str:
    m = {
        "launching": "🔵",
        "running": "🟢",
        "already_running": "🟢",
        "error": "🔴",
        "stopped": "🛑",
        "idle": "⚪",
    }
    return m.get(status, "⚪")

def _compute_menu_text(status: str) -> tuple[str, bool]:
    """
    Return (label, enabled) for the single menu item given a status.
    """
    emoji = _status_emoji(status)
    if status in ("running", "already_running"):
        return (f"Stop ComfyUI server  (Status: {emoji}running)", True)
    if status == "launching":
        return ("Status:🔵starting server...", False)
    if status == "error":
        return (f"Start ComfyUI Server (Status: {emoji}error)", True)
    if status == "stopped":
        return (f"Start ComfyUI Server (Status: {emoji}stopped)", True)
    # default idle and any unknown
    return (f"Start ComfyUI Server (Status: {emoji}idle)", True)

def _update_menu_item(status: str):
    """Ensure the single menu item exists, and update its label and enabled state."""
    global _MENU_ITEM_LABEL, _MENU_ITEM_NAME
    menu = _get_menu()
    if not menu:
        return
    _MENU_ITEM_LABEL, enabled = _compute_menu_text(status)
    try:
        # If the label changed (or wasn't set yet), replace the single item
        if _MENU_ITEM_NAME != _MENU_ITEM_LABEL:
            # Ensure the menu exists (re-acquire in case Nuke hid it)
            menu = _get_menu()
            if not menu:
                return
            # 1) Add the new item first if it doesn't already exist
            try:
                existing_new = menu.findItem(_MENU_ITEM_LABEL)  # type: ignore[attr-defined]
            except Exception:
                existing_new = None
            if not existing_new:
                menu.addCommand(_MENU_ITEM_LABEL, _toggle_server, index=0)
            # 2) Remove the old item after the new one exists to avoid an empty menu
            if _MENU_ITEM_NAME and _MENU_ITEM_NAME != _MENU_ITEM_LABEL:
                try:
                    menu.removeItem(_MENU_ITEM_NAME)  # type: ignore[attr-defined]
                except Exception:
                    pass
            _MENU_ITEM_NAME = _MENU_ITEM_LABEL
        # Try to set enabled state (and ensure item exists even if label didn't change)
        try:
            item = menu.findItem(_MENU_ITEM_NAME)  # type: ignore[attr-defined]
            if not item:
                # Item may have been removed or menu hidden; re-add it
                menu.addCommand(_MENU_ITEM_NAME, _toggle_server, index=0)
                item = menu.findItem(_MENU_ITEM_NAME)  # type: ignore[attr-defined]
            if item:
                item.setEnabled(enabled)  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception as e:
        nuke.tprint(f"[ComfyUi] Failed updating menu item: {e}")


def _on_status_change(status: str):
    # Called from background thread; ensure UI-safe update
    global _CURRENT_STATUS
    _CURRENT_STATUS = status
    try:
        nuke.executeInMainThread(_update_menu_item, args=(status,))  # type: ignore
    except Exception:
        _update_menu_item(status)


def _launch_and_wait():
    # Update menu immediately
    _on_status_change("launching")
    # Start server (non-blocking)
    launch_comfyui_server()
    # Wait for terminal state in a short-lived thread to avoid blocking UI
    def _waiter():
        status = wait_until_ready(timeout=45.0)
        _on_status_change(status)
    threading.Thread(target=_waiter, daemon=True).start()


def _toggle_server():
    """Menu command: start or stop depending on current status."""
    status = _CURRENT_STATUS
    if status in ("running", "already_running"):
        # Request stop
        try:
            stop_comfyui_server()
            _on_status_change("stopped")
        except Exception:
            _on_status_change("error")
    elif status == "launching":
        # Ignore clicks while launching
        return
    else:
        # idle, stopped, error, unknown -> launch
        _launch_and_wait()


# One-time cleanup of legacy menu entries, then create the single persistent item
_cleanup_legacy_menu_items()
_update_menu_item(_CURRENT_STATUS)

# Hook status callback and initialize label
try:
    set_status_callback(_on_status_change)
except Exception as e:
    nuke.tprint(f"[ComfyUi] Could not hook status callback: {e}")

# Initialize ComfyUI integration (optional if installed under ~/.nuke)
# try:
#     import nuke_comfyui as comfyui  # type: ignore
#     comfyui.setup()
#     nuke.tprint("[ComfyUi] nuke_comfyui loaded and initialized.")
# except ImportError:
#     nuke.tprint("[ComfyUi] nuke_comfyui not found. Skipping its setup.")