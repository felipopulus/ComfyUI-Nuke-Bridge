"""
ComfyUI-Nuke-Bridge (Lite) - Importer

Self-contained helper to import a ComfyUI workflow (UI JSON) and create a
roughly equivalent set of placeholder Nuke nodes and connections.

Scope (Phase 1):
- Supports reading a ComfyUI UI export JSON (LiteGraph format: nodes + links)
- Creates a Nuke node for each ComfyUI node using simple mappings when possible
  and falling back to a NoOp with a descriptive label
- Rebuilds basic connections (target input index is used when available, else 0)
- Positions nodes using the ComfyUI canvas positions

This is a foundation we can iterate on with a richer mapping table.
"""
from __future__ import annotations

import json
import os
import traceback
from typing import Any, Dict, List, Tuple

import nuke  # type: ignore


# ----------------------------- Utilities -------------------------------------

def _msg(text: str) -> None:
    try:
        nuke.tprint(f"[ComfyUi Import] {text}")
    except Exception:
        pass


def _safe_name(base: str) -> str:
    # Ensure a unique node name in the DAG
    name = base
    idx = 1
    while nuke.exists(name):
        idx += 1
        name = f"{base}_{idx}"
    return name


def _get_file_from_widgets(node: Dict[str, Any]) -> str | None:
    # Heuristic: many ComfyUI loader nodes place the file path as the first widget value
    w = node.get("widgets_values") or []
    if not isinstance(w, list) or not w:
        return None
    v = w[0]
    if isinstance(v, str) and v:
        return v
    return None


# ------------------------- Mapping Comfy -> Nuke ------------------------------

# Minimal initial mapping. Extend as needed.
NODE_TYPE_MAP = {
    "LoadImage": "Read",
    "SaveImage": "Write",
    "SaveImageSimple": "Write",
}


def _create_nuke_node_for_comfy(node: Dict[str, Any]) -> nuke.Node:
    ctype = node.get("type") or node.get("class_type") or "Unknown"
    nuke_class = NODE_TYPE_MAP.get(ctype, "NoOp")
    name = _safe_name(f"CU_{ctype}")

    # Build knobs script to set label and other defaults
    knobs_script = ""

    try:
        if nuke_class == "Read":
            # Prefer not to pop the panel
            n = nuke.createNode("Read", inpanel=False)
            n.setName(name)
            file_path = _get_file_from_widgets(node)
            if file_path:
                # If relative, leave as-is; user can adjust root
                n.knob("file").setValue(file_path)
            n.knob("label").setValue(f"{ctype}")
            return n
        elif nuke_class == "Write":
            n = nuke.createNode("Write", inpanel=False)
            n.setName(name)
            # Place a default output path to avoid validation issues
            out_dir = os.path.join(os.path.expanduser("~"), "ComfyUI_NukeBridge_Output")
            try:
                if not os.path.isdir(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
            except Exception:
                pass
            n.knob("file").setValue(os.path.join(out_dir, f"{name}.####.png").replace("\\", "/"))
            n.knob("colorspace").setValue("sRGB")
            n.knob("label").setValue(f"{ctype}")
            return n
        else:
            n = nuke.createNode("NoOp", inpanel=False)
            n.setName(name)
            n.knob("label").setValue(f"{ctype}")
            return n
    except Exception:
        # Fallback to a NoOp if something goes wrong creating a specific node
        n = nuke.createNode("NoOp", inpanel=False)
        n.setName(name)
        n.knob("label").setValue(f"{ctype}")
        return n


# ----------------------------- Import Core -----------------------------------

class ComfyUIWorkflow:
    def __init__(self, nodes: List[Dict[str, Any]], links: List[Any]):
        self.nodes = nodes
        self.links = links

    @staticmethod
    def from_json(data: Dict[str, Any]) -> "ComfyUIWorkflow":
        """
        Try to parse both LiteGraph-style export and potential alternative layout.
        Expected (LiteGraph): {"nodes": [...], "links": [[id, from, from_slot, to, to_slot, *], ...]}
        """
        nodes = data.get("nodes") or []
        links = data.get("links") or []
        # Some exports nest under a top-level key like "graph" or "workflow"
        if not nodes and isinstance(data.get("graph"), dict):
            g = data["graph"]
            nodes = g.get("nodes") or []
            links = g.get("links") or []
        return ComfyUIWorkflow(nodes=nodes, links=links)


def _compute_positions(nodes: List[Dict[str, Any]]) -> Dict[int, Tuple[int, int]]:
    pos: Dict[int, Tuple[int, int]] = {}
    for n in nodes:
        nid = n.get("id")
        p = n.get("pos") or n.get("position") or [0, 0]
        if isinstance(nid, int) and isinstance(p, (list, tuple)) and len(p) >= 2:
            # Comfy canvas is often a float canvas; Nuke expects ints
            x = int(float(p[0]))
            y = int(float(p[1]))
            pos[nid] = (x, y)
    return pos


def _connect_nodes(links: List[Any], by_id: Dict[int, nuke.Node]) -> int:
    connections = 0
    for link in links:
        try:
            # LiteGraph usually: [id, origin_node_id, origin_slot, target_node_id, target_slot, *]
            if isinstance(link, (list, tuple)) and len(link) >= 5:
                _, src_id, src_slot, dst_id, dst_slot, *rest = link
            elif isinstance(link, dict):
                # Alternative dict form
                src_id = link.get("from") or link.get("src") or link.get("output")
                dst_id = link.get("to") or link.get("dst") or link.get("input")
                src_slot = link.get("from_slot") or link.get("src_slot") or 0
                dst_slot = link.get("to_slot") or link.get("dst_slot") or 0
            else:
                continue

            if not isinstance(src_id, int) or not isinstance(dst_id, int):
                continue

            src = by_id.get(src_id)
            dst = by_id.get(dst_id)
            if not src or not dst:
                continue

            # Clamp to at most the max inputs of destination
            try:
                max_inputs = max(1, int(dst.maxInputs()))
            except Exception:
                max_inputs = 1
            slot = int(dst_slot) if isinstance(dst_slot, (int, float)) else 0
            if slot < 0 or slot >= max_inputs:
                slot = 0

            # Some nodes (e.g., Read) have 0 inputs, guard those
            try:
                if max_inputs > 0:
                    dst.setInput(slot, src)
                    connections += 1
            except Exception:
                # Ignore connection errors for now (e.g., incompatible classes)
                pass
        except Exception:
            # Skip malformed links while keeping the import running
            continue
    return connections


def import_comfyui_workflow() -> None:
    """Entry point called from the Nuke menu.

    Prompts the user for a ComfyUI workflow UI JSON file and creates placeholder
    nodes and connections in the current DAG.
    """
    try:
        file_path = nuke.getFilename("Open ComfyUI workflow JSON...", "*.json")  # type: ignore
    except Exception:
        file_path = None

    if not file_path:
        return

    if not os.path.isfile(file_path):
        nuke.message("Selected file does not exist.")  # type: ignore
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        nuke.message("Could not read JSON file. Check the format.")  # type: ignore
        _msg(traceback.format_exc())
        return

    wf = ComfyUIWorkflow.from_json(data)
    if not wf.nodes:
        nuke.message("No nodes found in the provided file.")  # type: ignore
        return

    positions = _compute_positions(wf.nodes)

    created: Dict[int, nuke.Node] = {}

    nuke.beginUndo("Import ComfyUI Workflow")
    try:
        # Create nodes first
        for n in wf.nodes:
            nid = n.get("id")
            if not isinstance(nid, int):
                continue
            nn = _create_nuke_node_for_comfy(n)
            # Position
            if nid in positions:
                x, y = positions[nid]
                try:
                    nn.setXYpos(x, y)
                except Exception:
                    pass
            # Tag with a text knob carrying original type and json blob for future upgrades
            try:
                if not nn.knob("comfy_type"):
                    nn.addKnob(nuke.Text_Knob("comfy_type", "comfy_type", str(n.get("type") or n.get("class_type") or "Unknown")))
                if not nn.knob("comfy_json"):
                    nn.addKnob(nuke.Multiline_Eval_String_Knob("comfy_json", "comfy_json", json.dumps(n)))
            except Exception:
                pass
            created[nid] = nn

        # Connect
        connected = _connect_nodes(wf.links, created)

    finally:
        nuke.endUndo()

    nuke.message(f"Imported {len(created)} nodes, connected {connected} links.")  # type: ignore


__all__ = [
    "import_comfyui_workflow",
]
