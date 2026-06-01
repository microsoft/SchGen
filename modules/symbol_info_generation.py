from __future__ import annotations
import os, sys
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

from modules.utils.custom_logger import setup_logger
from modules.sch_module_def import *
import my_skip_lib
from modules.utils.llm_interface import GetLLMInterface
from modules.utils.kicad_scan_lib import get_sym_context_with_cache, load_organized_lib
from typing import Any, Dict, List, Tuple, Optional

logger = setup_logger()
sym_lib_dict = load_organized_lib()
# llm = GetLLMInterface(model_name = "gpt-5.2", model_provider = "Azure")

def build_sym_context_infos(sch, sym_lib_dict) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]]]:
    """Build (symbol_lib, symbol_name) list + context infos with bbox + pins."""

    def _unq(s):
        """Unquote KiCad strings like '"VDD"' -> 'VDD'."""
        if isinstance(s, str):
            s = s.strip()
            if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                return s[1:-1]
        return s

    def _to_float(x) -> float:
        try:
            return float(_unq(x))
        except Exception:
            return float(x)

    def _orientation_from_deg(deg: float) -> str:
        """
        KiCad rotations are degrees.
        Commonly: 0=right, 180=left, 90=up, 270=down (depending on pin direction conventions).
        We'll map to Right/Left/Up/Down labels.
        """
        d = deg % 360
        if d == 0:
            return "Right"
        if d == 90:
            return "Up"
        if d == 180:
            return "Left"
        if d == 270:
            return "Down"
        # fallback for non-cardinal rotations
        return f"{d:.0f}deg"

    def _iter_nodes(tree: Any):
        """Yield every list node in a nested list tree."""
        if isinstance(tree, list):
            yield tree
            for item in tree:
                yield from _iter_nodes(item)

    def _extract_bbox_and_pins(sym_info: Dict[str, Any], lib_name: str, symbol_name: str) -> Dict[str, Any]:
        """
        Parse sym_info["symbol"] (nested list) to:
          - bbox from rectangles
          - pins from pin nodes
        """
        sym_tree = sym_info.get("symbol", [])
        rect_points: List[Tuple[float, float]] = []
        pins: List[Dict[str, Any]] = []

        for node in _iter_nodes(sym_tree):
            if not node:
                continue

            # rectangle: ['rectangle', ['start', x, y], ['end', x, y], ...]
            if node[0] == "rectangle":
                start = None
                end = None
                for child in node[1:]:
                    if isinstance(child, list) and child:
                        if child[0] == "start" and len(child) >= 3:
                            start = (_to_float(child[1]), _to_float(child[2]))
                        elif child[0] == "end" and len(child) >= 3:
                            end = (_to_float(child[1]), _to_float(child[2]))
                if start and end:
                    rect_points.extend([start, end])

            # pin: ['pin', <etype>, <shape>, ['at', x, y, rot], ['length', ...], ['name', ...], ['number', ...], ...]
            if node[0] == "pin":
                at_x = at_y = rot = None
                pin_name = None
                pin_number = None

                for child in node[1:]:
                    if isinstance(child, list) and child:
                        tag = child[0]
                        if tag == "at" and len(child) >= 4:
                            at_x = _to_float(child[1])
                            at_y = _to_float(child[2])
                            rot = _to_float(child[3])
                        elif tag == "name" and len(child) >= 2:
                            pin_name = _unq(child[1])
                        elif tag == "number" and len(child) >= 2:
                            pin_number = _unq(child[1])

                # Only keep pins that have the essentials
                if pin_name is not None and pin_number is not None and at_x is not None and at_y is not None:
                    if pin_name == "~":  # parameter-driven pin, use number as name
                        pin_name = pin_number
                    pins.append(
                        {
                            "pin_name": str(pin_name),
                            "x": float(at_x),
                            "y": float(at_y),
                            "orientation": _orientation_from_deg(float(rot or 0.0)),
                        }
                    )

        # --- bbox: collect ALL geometry points (rectangle endpoints, polylines, etc.) ---
        geom_points: List[Tuple[float, float]] = []

        for node in _iter_nodes(sym_tree):
            if not node:
                continue

            # Keep your existing pin extraction unchanged ...

            # Collect any ['xy', x, y] we can find anywhere (polyline/pts, arcs, etc.)
            if node[0] == "xy" and len(node) >= 3:
                geom_points.append((_to_float(node[1]), _to_float(node[2])))

            # Also keep rectangle endpoints (some rectangles don't appear as 'xy' nodes)
            if node[0] == "rectangle":
                start = end = None
                for child in node[1:]:
                    if isinstance(child, list) and child:
                        if child[0] == "start" and len(child) >= 3:
                            start = (_to_float(child[1]), _to_float(child[2]))
                        elif child[0] == "end" and len(child) >= 3:
                            end = (_to_float(child[1]), _to_float(child[2]))
                if start and end:
                    geom_points.extend([start, end])

        if geom_points:
            xs = [p[0] for p in geom_points]
            ys = [p[1] for p in geom_points]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
        else:
            bbox = []

        return {
            "symbol_name": str(symbol_name),
            "lib_name": str(lib_name),
            "Bounding_box": bbox,
            "pin_info": pins,
        }

    sym_list: List[Tuple[str, str]] = []
    sym_context_infos: List[Dict[str, Any]] = []
    visited_lib_ids = set()

    for component in getattr(sch, "symbol", []):
        lib_id = getattr(component.lib_id, "value", None)
        if not lib_id or lib_id in visited_lib_ids:
            continue
        visited_lib_ids.add(lib_id)

        if ":" in lib_id:
            symbol_lib, symbol_name = lib_id.split(":", 1)
        else:
            symbol_lib, symbol_name = lib_id, ""

        sym_list.append((symbol_lib, symbol_name))

        # find the library record, then parse bbox + pins
        for sym_info in sym_lib_dict.get(symbol_lib, []):
            if _unq(sym_info.get("name", "")) == symbol_name:
                ctx = _extract_bbox_and_pins(sym_info, lib_name=symbol_lib, symbol_name=symbol_name)
                sym_context_infos.append(ctx)
                break

    return sym_list, sym_context_infos

def describe_symbol_info(sch):
    
    sym_list, sym_context_infos = build_sym_context_infos(sch, sym_lib_dict)

    symbol_context = {}
    for i, ctx in enumerate(sym_context_infos, start=1):
        symbol_context[f"symbol#{i}"] = ctx
    
    return symbol_context
    


if __name__ == "__main__":
    sch_path = "/home/v-luoqinpei/workspace/llm4circuit/dataset/15335_9DoF_Schematic/sch_1_0.kicad_sch"
    sch = my_skip_lib.Schematic(sch_path)

    sym_list, sym_context_infos = build_sym_context_infos(sch, sym_lib_dict)

    symbol_context = {}
    for i, ctx in enumerate(sym_context_infos, start=1):
        symbol_context[f"symbol#{i}"] = ctx

    # return / save / print
    print(symbol_context)