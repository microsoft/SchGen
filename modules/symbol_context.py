'''
Symbol information generation for KiCad schematic symbols.
The main function `get_symbol_context` takes a schematic object, extracts the symbol information, including their bounding boxes and pin details, and organizes this information into a structured dictionary format. The script uses helper functions to parse the symbol descriptions, calculate bounding boxes from geometry points, and determine pin orientations based on their rotation. The output is a comprehensive context for each symbol that can be used for further processing or analysis in the PCB layout generation pipeline.
'''

from __future__ import annotations
from typing import Any, Dict, List, Tuple
import os
import sys
from pathlib import Path

proj_path = Path(os.environ["PROJECT_PATH"])
sys.path.append(str(proj_path))

from modules.utils.kicad_scan_lib import load_organized_lib
import my_skip_lib  # Your custom library for parsing KiCad schematics
from modules.sch_module_def import RelatedSymbols, rRelatedSymbols
from modules.utils.kicad_scan_lib import load_organized_lib


# Expect these to exist in your environment:
#   - my_skip_lib.Schematic
#   - sym_lib_dict  (dict: lib_name -> list[dict], each dict like your examples)
# If you use Pydantic in your project, you can swap the returned dicts into models easily.

sym_lib_dict = load_organized_lib()

def build_sym_context_infos(sch_or_symbols) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]]]:
    """Build (symbol_lib, symbol_name) list + context infos with bbox + pin_info.

    Supports:
      1) KiCad schematic object with sch.symbol
      2) List[str] like ["RF:nRF24L01P", "MCU_ST_STM32WB:STM32WBA52CEUx"]
    """

    def _unq(s):
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
        if isinstance(tree, list):
            yield tree
            for item in tree:
                yield from _iter_nodes(item)

    def _extract_bbox_and_pins(
        sym_info: Dict[str, Any],
        lib_name: str,
        symbol_name: str,
        description: str = "",
    ) -> Dict[str, Any]:
        sym_tree = sym_info.get("symbol", [])
        geom_points: List[Tuple[float, float]] = []
        pins: List[Dict[str, Any]] = []

        for node in _iter_nodes(sym_tree):
            if not node:
                continue

            if node[0] == "xy" and len(node) >= 3:
                geom_points.append((_to_float(node[1]), _to_float(node[2])))

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
                        pin_name = pin_number

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
            "Bounding_box": bbox,
            "pin_info": pins,
        }

    def _resolve_symbol_info(symbol_lib: str, symbol_name: str):
        """Find symbol info from sym_lib_dict, including extends support."""
        for sym_info in sym_lib_dict.get(symbol_lib, []):
            if _unq(sym_info.get("name", "")) == symbol_name:
                description = sym_info.get("description", "")
                new_sym_name = _unq(sym_info.get("extends", ""))

                if new_sym_name:
                    for ext_sym_info in sym_lib_dict.get(symbol_lib, []):
                        if _unq(ext_sym_info.get("name", "")) == new_sym_name:
                            new_sym_info = dict(ext_sym_info)
                            new_sym_info["name"] = symbol_name
                            return new_sym_info, description

                return sym_info, description

        return None, ""

    def _parse_lib_id(lib_id: str) -> Tuple[str, str]:
        lib_id = _unq(lib_id)
        if ":" in lib_id:
            return lib_id.split(":", 1)
        return lib_id, ""

    # ---- collect lib_ids from either sch object or list[str]
    lib_ids: List[str] = []

    if isinstance(sch_or_symbols, list):
        for item in sch_or_symbols:
            if isinstance(item, str):
                lib_ids.append(item)
            elif isinstance(item, tuple) and len(item) == 2:
                lib_ids.append(f"{item[0]}:{item[1]}")
            else:
                raise TypeError(f"Unsupported symbol list item: {item}")
    else:
        for component in getattr(sch_or_symbols, "symbol", []):
            lib_id = getattr(component.lib_id, "value", None)
            if lib_id:
                lib_ids.append(lib_id)

    # ---- main lookup
    sym_list: List[Tuple[str, str]] = []
    sym_context_infos: List[Dict[str, Any]] = []
    visited_lib_ids = set()

    for lib_id in lib_ids:
        lib_id = _unq(lib_id)

        if not lib_id or lib_id in visited_lib_ids:
            continue

        visited_lib_ids.add(lib_id)

        symbol_lib, symbol_name = _parse_lib_id(lib_id)
        sym_list.append((symbol_lib, symbol_name))

        matched, description = _resolve_symbol_info(symbol_lib, symbol_name)

        if matched is not None:
            ctx = _extract_bbox_and_pins(
                matched,
                lib_name=symbol_lib,
                symbol_name=symbol_name,
                description=description,
            )
            sym_context_infos.append(ctx)

    return sym_list, sym_context_infos


def get_symbol_context(sch) -> Dict[str, Dict[str, Any]]:
    """Build and organize symbol context as {'symbol#1': ctx1, 'symbol#2': ctx2, ...}."""
    _, sym_context_infos = build_sym_context_infos(sch)
    return {f"symbol#{i}": ctx for i, ctx in enumerate(sym_context_infos, start=1)}

def get_symbol_context_from_list(selected_symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Build and organize symbol context as {'symbol#1': ctx1, 'symbol#2': ctx2, ...}."""
    _, sym_context_infos = build_sym_context_infos(selected_symbols)
    return {f"symbol#{i}": ctx for i, ctx in enumerate(sym_context_infos, start=1)}


def load_related_symbols(llm, sch_request: str, img_ref_path: str = None, img_ref_description: str = None,
                         organized_lib_path: str = "./export/organized_lib.json", logger=None):
    """
    Load related schematic symbols for a request using an LLM and KiCad library metadata.
    """
    if logger:
        logger.info("Loading related symbols...")

    sym_lib_dict = load_organized_lib(organized_lib_path)
    if logger:
        logger.info("Organized lib info loaded.")

    ref_img_require = "Make sure include librates and symbols that are used in the reference image description below "
    find_lib_question = f"""
    Find the related schematic libraries for the following user request for a circuit schematic: {sch_request}
    {ref_img_require + '\n' + img_ref_description if img_ref_path is not None else ""}
    ###
    We have the following components library as listed below:
    {list(sym_lib_dict.keys())}
    ###
    NOTE:
    You must use the component name exactly as listed above, without quotes, and the component name is case sensitive. Check the image description carefully and identify the libraries that are related to it. You MUST ONLY INCLUDE the components in the library, DO NOT include any other components that are not in the library.
    """

    if img_ref_path is not None:
        local_msg = llm.prepare_input_with_image(find_lib_question, img_ref_path)
    else:
        local_msg = [{"role": "user", "content": find_lib_question}]

    response, data_obj = llm.get_json_response_retry(local_msg, rRelatedSymbols)
    if logger:
        logger.info(f"Response: {response}")
        logger.info(f"Related libs object: {data_obj}")

    filtered_libs = []
    for sym in data_obj.symbols:
        for lib_name, sym_list in sym_lib_dict.items():
            if any(sym_info.get("name") == sym for sym_info in sym_list):
                filtered_libs.append(lib_name)
                break

    if "Device" not in filtered_libs:
        filtered_libs.append("Device")
    if "power" not in filtered_libs:
        filtered_libs.append("power")

    filtered_lib_info = {}
    for lib_name in filtered_libs:
        assert lib_name in sym_lib_dict, f"Library {filtered_libs} not found in the organized library."

        minimal_sym_info = []
        for sym_info in sym_lib_dict[lib_name]:
            tmp_info = sym_info.copy()
            tmp_info["symbol"] = ""
            tmp_info["datasheet"] = ""
            tmp_info["footprint"] = ""
            minimal_sym_info.append(tmp_info)

        filtered_lib_info[lib_name] = minimal_sym_info

    if logger:
        logger.info("Filtered lib info Done.")

    symbol_list = []
    truncate_len = 500e3
    ask_times = int(len(str(filtered_lib_info)) // truncate_len + 1)
    lib_ct = 0

    for i in range(ask_times):
        tmp_lib_info = {}
        for j in range(lib_ct, len(filtered_libs), 1):
            if len(str(tmp_lib_info)) + len(str(filtered_lib_info[filtered_libs[j]])) > truncate_len:
                break
            tmp_lib_info[filtered_libs[j]] = filtered_lib_info[filtered_libs[j]]
            lib_ct = j + 1

        formatted_lib_info = ""
        for lib_name, sym_list in tmp_lib_info.items():
            for sym_info in sym_list:
                formatted_lib_info += f"Name: {sym_info['name']}, Library: {lib_name}, description: {sym_info['description']}\n"

        if logger:
            logger.info(f"Asking LLM for related symbols ({i+1} / {ask_times})")

        find_symbol_question = f"""
        Find the related schematic symbols for the following user request for a circuit schematic: {sch_request}
        {ref_img_require if img_ref_path is not None else ""}
        ###
        We have the following Symbols in different libraries as listed below:
        {formatted_lib_info}
        ###
        NOTE:
        1. You should include all related symbols, even for simple components like resistors, capacitors, and inductors, power symbols.
        """

        if img_ref_path is not None:
            local_msg = llm.prepare_input_with_image(find_symbol_question, img_ref_path)
        else:
            local_msg = [{"role": "user", "content": find_symbol_question}]

        response, data_obj = llm.get_json_response_retry(local_msg, RelatedSymbols)
        if logger:
            logger.info(f"Response: {response}")
            logger.info(f"Related symbols object: {data_obj}")

        symbol_list += data_obj.symbols

    return symbol_list


def describe_symbol_info(symbol_list: list, logger=None):
    """
    Build a symbol context string from a symbol list.
    """
    if logger:
        logger.info("Describing symbol info...")

    sym_list = [f"{sym.lib_name}:{sym.name}" for sym in symbol_list]
    symbol_context = get_symbol_context_from_list(sym_list)

    if logger:
        logger.info(symbol_context)

    return symbol_context

if __name__ == "__main__":
    # ---- your inputs (these must already exist in your project)
    sch_path = ""

    # Provided by your environment:
    #   my_skip_lib.Schematic
    #   sym_lib_dict
    sch = my_skip_lib.Schematic(sch_path)

    symbol_context = get_symbol_context(sch)

    print(symbol_context)