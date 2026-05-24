from __future__ import annotations
from typing import Any, Dict, List, Tuple
import os
import sys
from pathlib import Path

proj_path = Path(os.environ["PROJECT_PATH"])
sys.path.append(str(proj_path))

from modules.utils.kicad_scan_lib import load_organized_lib
import my_skip_lib  # Your custom library for parsing KiCad schematics


# Expect these to exist in your environment:
#   - my_skip_lib.Schematic
#   - sym_lib_dict  (dict: lib_name -> list[dict], each dict like your examples)
# If you use Pydantic in your project, you can swap the returned dicts into models easily.

sym_lib_dict = load_organized_lib()

def build_sym_context_infos(sch) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]]]:
    """Build (symbol_lib, symbol_name) list + context infos with bbox + pin_info."""

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
        d = deg % 360
        if d == 0:
            return "Right"
        if d == 90:
            return "Up"
        if d == 180:
            return "Left"
        if d == 270:
            return "Down"
        return f"{d:.0f}deg"

    def _iter_nodes(tree: Any):
        """Yield every list node in a nested list tree."""
        if isinstance(tree, list):
            yield tree
            for item in tree:
                yield from _iter_nodes(item)

    def _extract_bbox_and_pins(sym_info: Dict[str, Any], lib_name: str, symbol_name: str, description: str = "") -> Dict[str, Any]:
        """
        Parse sym_info["symbol"] (nested list) to:
          - bbox from geometry points (polyline xy, etc.) + rectangle start/end
          - pins from pin nodes
        """
        sym_tree = sym_info.get("symbol", [])
        geom_points: List[Tuple[float, float]] = []
        pins: List[Dict[str, Any]] = []

        for node in _iter_nodes(sym_tree):
            if not node:
                continue

            # --- bbox: collect generic geometry points like ['xy', x, y] (polyline, etc.)
            if node[0] == "xy" and len(node) >= 3:
                geom_points.append((_to_float(node[1]), _to_float(node[2])))

            # --- bbox: also collect rectangle endpoints (sometimes no nested 'xy' nodes)
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

            # --- pins (unchanged logic)
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

                if (
                    pin_name is not None
                    and pin_number is not None
                    and at_x is not None
                    and at_y is not None
                ):
                    if pin_name == "~":
                        pin_name = pin_number  # Fallback to number if name is "~"
                    pins.append(
                        {
                            "pin_name": str(pin_name),
                            "x": float(at_x),
                            "y": float(at_y),
                            "orientation": _orientation_from_deg(float(rot or 0.0)),
                        }
                    )

        if geom_points:
            xs = [p[0] for p in geom_points]
            ys = [p[1] for p in geom_points]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
        else:
            bbox = []

        return {
            "symbol_name": str(symbol_name),
            "lib_name": str(lib_name),
            "description": str(description),
            "Bounding_box": bbox,   # [x_min, y_min, x_max, y_max]
            "pin_info": pins,       # list[dict]
        }

    # ---- main lookup
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

        # find matching symbol record in the library dict
        matched = None
        for sym_info in sym_lib_dict.get(symbol_lib, []):
            if _unq(sym_info.get("name", "")) == symbol_name:
                new_sym_name = _unq(sym_info.get("extends", ""))
                description = sym_info.get("description", "")
                if new_sym_name != "":
                    for ext_sym_info in sym_lib_dict.get(symbol_lib, []):
                        if _unq(ext_sym_info.get("name", "")) == new_sym_name:
                            new_sym_info = dict(ext_sym_info)
                            new_sym_info["name"] = symbol_name  # Override with the actual symbol name used
                            matched = new_sym_info
                            break
                else:
                    matched = sym_info
                    break
                break

        if matched is not None:
            ctx = _extract_bbox_and_pins(matched, lib_name=symbol_lib, symbol_name=symbol_name, description=description)
            sym_context_infos.append(ctx)

    return sym_list, sym_context_infos


def get_symbol_context(sch) -> Dict[str, Dict[str, Any]]:
    """Build and organize symbol context as {'symbol#1': ctx1, 'symbol#2': ctx2, ...}."""
    _, sym_context_infos = build_sym_context_infos(sch)
    return {f"symbol#{i}": ctx for i, ctx in enumerate(sym_context_infos, start=1)}

if __name__ == "__main__":
    # ---- your inputs (these must already exist in your project)
    sch_path = "/Users/luoqinpei/Workspace/llm4circuit/dataset/Qwiic_Twist_Schematic/sch_0_1.kicad_sch"

    # Provided by your environment:
    #   my_skip_lib.Schematic
    #   sym_lib_dict
    sch = my_skip_lib.Schematic(sch_path)

    symbol_context = get_symbol_context(sch)

    print(symbol_context)