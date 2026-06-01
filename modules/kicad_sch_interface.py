'''
This module provides an interface to interact with KiCad schematic files (.kicad_sch) using the kicad-skip library. It includes functions to add symbols, wires, labels, and junctions to the schematic, as well as to check for overlaps and manage connections. The module also handles coordinate transformations and maintains a mapping of symbol names to their corresponding libraries for more robust symbol resolution. This interface is designed to be used in an LLM-based schematic design workflow, allowing for programmatic manipulation of KiCad schematics based on design requirements and feedback.
'''

import sys
import os
# open config file to get the project path
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

from modules.utils.kicad_add_symbol import add_symbol_from_lib, check_position_overlap_error, check_box_overlap_error
from modules.utils.pin_matcher import find_best_pin_instance
from config import KICAD_SYMBOL_LIB_PATH
from modules.utils.kicad_scan_lib import  load_organized_fp
from modules.utils.misc import *
from collections import defaultdict
from typing import Optional, Dict, Any, List
import json
from difflib import SequenceMatcher

import uuid
from pathlib import Path
import re

def append_kicad_wire_raw(sch_path, start_pos, end_pos):
    p = Path(sch_path)
    txt = p.read_text(encoding="utf-8")

    wire_text = f'''
    (wire
        (pts
            (xy {start_pos[0]} {start_pos[1]})
            (xy {end_pos[0]} {end_pos[1]})
        )
        (stroke
            (width 0.25)
            (type default)
        )
        (uuid {uuid.uuid4()})
    )
'''

    # Match "(sheet_instances" with any whitespace before it.
    m = re.search(r'\s*\(sheet_instances\b', txt)
    if not m:
        raise RuntimeError("Cannot find top-level sheet_instances insertion point.")

    insert_pos = m.start()
    txt = txt[:insert_pos] + "\n" + wire_text + "\n" + txt[insert_pos:]

    p.write_text(txt, encoding="utf-8")

def _normalize_sym(s: str) -> str:
    """
    Normalize symbol name for fuzzy matching:
    - strip
    - lowercase
    - collapse whitespace
    - unify separators (space, '-', multiple '_') into single '_'
    """
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[-]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s


# module-level cache
_ALL_SYMBOLS_CACHE: Dict[str, List[str]] = {}


def _all_symbols_from_lib_tree(project_path: str) -> List[str]:
    global _ALL_SYMBOLS_CACHE

    # Use project_path as key (in case you have multiple projects)
    if project_path in _ALL_SYMBOLS_CACHE:
        return _ALL_SYMBOLS_CACHE[project_path]

    lib_tree_path = Path(project_path) / "modules" / "component_repository.json"
    data: Dict[str, Any] = json.loads(lib_tree_path.read_text(encoding="utf-8"))

    symbols: List[str] = []
    for _lvl1_name, lvl2_dict in data.items():
        if not isinstance(lvl2_dict, dict):
            continue
        for _lvl2_name, lib_dict in lvl2_dict.items():
            if not isinstance(lib_dict, dict):
                continue
            for _symbol_lib, symbol_list in lib_dict.items():
                if not isinstance(symbol_list, list):
                    continue
                for sym in symbol_list:
                    if isinstance(sym, str):
                        symbols.append(sym)

    # cache it
    _ALL_SYMBOLS_CACHE[project_path] = symbols
    return symbols


def _score(query_norm: str, cand_norm: str) -> float:
    """
    Similarity score. Higher is better.
    Base: SequenceMatcher ratio.
    Bonus: substring containment and token overlap.
    """
    if query_norm == cand_norm:
        return 10.0  # guaranteed best

    base = SequenceMatcher(None, query_norm, cand_norm).ratio()  # [0,1]

    bonus = 0.0
    if query_norm in cand_norm or cand_norm in query_norm:
        bonus += 0.15

    q_tokens = set(query_norm.split("_"))
    c_tokens = set(cand_norm.split("_"))
    if q_tokens and c_tokens:
        jacc = len(q_tokens & c_tokens) / max(1, len(q_tokens | c_tokens))
        bonus += 0.20 * jacc

    return base + bonus


def best_symbol_name_from_lib_tree(
    symbol_name: str,
    project_path: str,
    min_score: float = 0.5,
) -> Optional[str]:
    """
    Input:  symbol_name (pure, e.g., "C", "Conn_01x02", "R_Array_4")
    Output: best matching symbol_name that exists in component_repository.json

    If exact match exists, returns immediately.
    Else fuzzy match and return best candidate if its score >= min_score.
    Else returns None (you can choose to fallback to original name).
    """
    all_syms = _all_symbols_from_lib_tree(project_path)
    if not all_syms:
        return None

    # 1) exact match
    sym_set = set(all_syms)
    if symbol_name in sym_set:
        return symbol_name

    # 2) normalized exact match (handles case/spacing/underscore variants)
    qn = _normalize_sym(symbol_name)
    norm_to_original: Dict[str, str] = {}
    for s in all_syms:
        norm_to_original.setdefault(_normalize_sym(s), s)

    if qn in norm_to_original:
        return norm_to_original[qn]

    # 3) fuzzy match
    best = None
    best_sc = -1.0
    for s in all_syms:
        sc = _score(qn, _normalize_sym(s))
        if sc > best_sc:
            best_sc = sc
            best = s

    if best is None or best_sc < min_score:
        return None

    return best



## Local dict that records connection relations between two points.
# direct connections: one wire connection, no bent or multi-segment wire.
direct_connections = defaultdict(set)
# junction connections: two or more wires connected with junction points. Can be L shaped or T shaped.
junction_connections = defaultdict(set)
coord_to_block = {}  # This is used to record the block mapping for the schematic symbols.

sch_filename = get_schematic_path() # Get the default schematic file path from the config file.

_SYMBOL_TO_LIB_CACHE: Optional[Dict[str, str]] = None

def _build_symbol_to_lib_index() -> Dict[str, str]:
    """
    Build a mapping: symbol_name -> symbol_lib
    Ignores the first two hierarchy levels.
    First match wins if a symbol_name appears multiple times.
    """
    lib_tree_path = Path(project_path) / "modules" / "component_repository.json"
    data: Dict[str, Any] = json.loads(lib_tree_path.read_text(encoding="utf-8"))

    symbol_to_lib: Dict[str, str] = {}

    # data structure: {L1: {L2: {symbol_lib: [symbol_names...]}}}
    for _lvl1_name, lvl2_dict in data.items():
        if not isinstance(lvl2_dict, dict):
            continue
        for _lvl2_name, lib_dict in lvl2_dict.items():
            if not isinstance(lib_dict, dict):
                continue

            for symbol_lib, symbol_list in lib_dict.items():
                if not isinstance(symbol_list, list):
                    continue

                for sym in symbol_list:
                    if not isinstance(sym, str):
                        continue
                    # first match wins
                    if sym not in symbol_to_lib:
                        symbol_to_lib[sym] = symbol_lib

    return symbol_to_lib


def _resolve_symbol_lib(symbol_name: str) -> Optional[str]:
    global _SYMBOL_TO_LIB_CACHE
    if _SYMBOL_TO_LIB_CACHE is None:
        _SYMBOL_TO_LIB_CACHE = _build_symbol_to_lib_index()
    return _SYMBOL_TO_LIB_CACHE.get(symbol_name)

def set_schematic_filename(filename: str = None):
    """
    Set the schematic filename to be used in the module.
    """
    global sch_filename
    sch_filename = filename if filename else get_schematic_path()


def add_point_connection(p1, p2, connections: defaultdict):
    """
    Add two points to the `connections` set to record a two-way connection. 
    """
    connections[tuple(p1)].add(tuple(p2))
    connections[tuple(p2)].add(tuple(p1))



def midpoint(p1, p2):

    return [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]

def coordinate_to_kicad(x, y):
    # Convert coordinates from local X-Y axes in the image to KiCad's X-Y axes

    local_origin = (75, 50) # unit is in mil (1/1000 inch)

    local_unit = 10

    kicad_x = x*local_unit + local_origin[0]
    kicad_y = local_origin[1] + 100 - y*local_unit

    return kicad_x, kicad_y


def add_schematic_symbol(symbol_lib="RF_Module", symbol_name="ESP-WROOM-02", pos_x=150, pos_y=100, reference="U1", value="", rotation=0, mirror:str =None):

    if isinstance(pos_x, int):
        pos_x *= 1.27
    if isinstance(pos_y, int):
        pos_y *= 1.27

    if REVERSE_Y_FLAG:
        pos_y = reY(pos_y)

    # If the symbol name is not provided, then it means it is a module/IC, so we need to set the value to the symbol name
    if value == "":
        value = symbol_name
        # assert reference.startswith("U"), "Reference must start with U for modules/ICs"


    # Process mirror value to standard format.
    if mirror is not None and mirror != "None" and mirror != "none" and mirror != "":
        # Set the mirror direction
        if mirror == "X" or mirror == "x":
            mirror_val = 'x'
        elif mirror == "Y" or mirror == "y":
            mirror_val = 'y'
        else:
            print(f"Warning: Invalid mirror direction '{mirror}' specified. It should be 'x' or 'y'.")
            raise ValueError(f"Invalid mirror direction: {mirror}. Must be 'x' or 'y'.")
    else:
        mirror_val = None

    # --- resolve symbol_name from component_repository.json (more robust) ---
    symbol_name = best_symbol_name_from_lib_tree(symbol_name=symbol_name, project_path=project_path) or symbol_name

    # --- resolve symbol_name from component_repository.json (more robust) ---
    resolved_lib = _resolve_symbol_lib(symbol_name)
    if resolved_lib is not None:
        if resolved_lib != symbol_lib:
            print(f"Info: symbol_name='{symbol_name}' found in component_repository.json, using symbol_lib='{resolved_lib}' instead of provided symbol_lib='{symbol_lib}'.")
            symbol_lib = resolved_lib
    else:
        # keep user-provided symbol_lib as fallback
        print(f"Warning: symbol_name='{symbol_name}' not found in component_repository.json. "
              f"Falling back to provided symbol_lib='{symbol_lib}'.")

    # Example: Add a symbol to a schematic
    add_symbol_from_lib(
        sch_filename=sch_filename,
        sym_filename= Path(KICAD_SYMBOL_LIB_PATH )/ (symbol_lib + ".kicad_sym"),
        symbol_name=symbol_name,
        lib_name=symbol_lib,
        x=pos_x,
        y=pos_y,
        rotation=rotation,
        reference=reference,
        value=value,
        mirror=mirror_val,
        output_filename=None
    )

    # Update: no need for mirror here, moved to add_symbol_from_lib() above.
    # mirror_symbol(reference, mirror)


# pip install kicad-skip>=0.2.5
## NOTE: Original skip library has bugs, so use our local modified version.
import my_skip_lib 

#  Loading / Saving
def load_schematic(path: str) -> my_skip_lib.Schematic:
    """Return a Schematic object for the given .kicad_sch path."""
    return my_skip_lib.Schematic(path)

def save_schematic(schematic: my_skip_lib.Schematic, out_path: str):
    """Write the schematic back to disk."""
    schematic.write(out_path)

def save_code(code: str, out_path: str):
    """Write the code to a file."""
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(code)

def save_description(description: str, out_path: str):
    """Write the description to a file."""
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(description)

def align_to_grid(x, grid_size=1.27):
    """
    Align the position to the grid.

    Args:
        x (float): The position to align.
        grid_size (float): The size of the grid. Default is 1.27mm.
    """
    return round(x / grid_size) * grid_size

def change_unit_to_grid(x, grid_size=1.27):
    """
    Change the position unit to grid unit.

    Args:
        x (float): The position to change.
        grid_size (float): The size of the grid. Default is 1.27mm.
    """
    return round(x / grid_size)


def add_junction(junc_pos: list, reY_off: bool = False):
    """
    Add a junction to the schematic. 

    Args:
        junc_pos (tuple): The position of the junction (x, y).
    """

    if isinstance(junc_pos, tuple):
        junc_pos = list(junc_pos)

    if REVERSE_Y_FLAG and not reY_off:
        junc_pos = junc_pos.copy()  # Create a copy to avoid modifying the original list
        junc_pos[1] = reY(junc_pos[1])

    schematic = load_schematic(sch_filename)

    # Add the junction to the schematic
    junction = schematic.junction.new()
    junction.move(align_to_grid(junc_pos[0]), align_to_grid(junc_pos[1]))

    # Save the schematic
    save_schematic(schematic, sch_filename)

sch_label_map = {}  # This is used to register the labels in the schematic.

def add_label(label_pos: list, label_text: str, label_ref: str, label_type: str = "input", text_orient: str ="left"):
    """
    Add a label to the schematic. Meanwhile register its unique ID.
    TODO: allow both global and net labels to be added.
    """

    global sch_label_map

    # assert label_ref has not exist in sch_label_map
    if label_ref in sch_label_map:
        raise ValueError(f"Label reference {label_ref} already exists in the schematic. Please use a unique label reference.")
    sch_label_map[label_ref] = label_pos

    add_global_label(label_pos, label_text, label_ref, label_type, text_orient)


def add_global_label(label_pos: list, label_text: str, label_ref: str, label_type: str = "input", text_orient: str ="left"):
    """
    Add a global label to the schematic. 

    Args:
        label_pos (tuple): The position of the label (x, y).
        label_text (str): The text of the label.
        label_type (str): The type of the label. Default is "input". Other options are "output", "bidirectional", "passive" etc.
        text_orient (str): The orientation of the label text relative to the pin position. Default is "left". Other options are "right", "top", "bottom".
    """

    if REVERSE_Y_FLAG:
        label_pos = label_pos.copy() if isinstance(label_pos, list) else list(label_pos)  # Create a copy to avoid modifying the original list
        label_pos[1] = reY(label_pos[1])
    

    schematic = load_schematic(sch_filename)

    # Add the global label to the schematic
    global_label = schematic.global_label.new()
    global_label.value = label_text
    
    if label_type not in ["input", "output", "bidirectional", "passive"]:
        if RAISE_ERR_FLAG:
            raise ValueError(f"Invalid label type: {label_type}. Must be one of 'input', 'output', 'bidirectional', 'passive'.")
        else:
            label_type = "bidirectional"
            print("Error: Invalid label type. Defaulting to 'bidirectional'.")

    global_label.shape.value = label_type # Set the label type to input, output, bidirectional, etc.

    # Set the position of the label text relative to the pin position
    if text_orient == "left":
        angle = 180
        orientation = "right"
    elif text_orient == "right":
        angle = 0
        orientation = "left"
    elif text_orient == "top" or text_orient == "up":
        angle = 90
        orientation = "left"
    elif text_orient == "bottom" or text_orient == "down":
        angle = 270
        orientation = "right"
    else:
        raise ValueError(f"Invalid text orientation: {text_orient}. Must be one of 'left', 'right', 'top', 'bottom'.")
    
    label_pos = [align_to_grid(label_pos[0]), align_to_grid(label_pos[1])]  # Align the position to the grid

    global_label.move(label_pos[0], label_pos[1], angle)
    global_label.effects.justify.value = orientation  # "left", "right"

    # Save the schematic
    save_schematic(schematic, sch_filename)

    # Check for position overlap error
    # check_position_overlap_error("Global Label", label_text, label_pos[0], label_pos[1])
    length, width = 1.27 + 1.27*len(label_text.replace(r"{slash}", "/")), 1*2  # Size of the label box in mm
    # width is a bit smaller than actual size to avoid overlap warning due to side by side label placement.
    if text_orient == "left":
        label_box = (label_pos[0] - length, label_pos[1] - width/2, label_pos[0], label_pos[1] + width/2)
    elif text_orient == "right":
        label_box = (label_pos[0], label_pos[1] - width/2, label_pos[0] + length, label_pos[1] + width/2)
    elif text_orient == "top" or text_orient == "up":
        label_box = (label_pos[0] - width/2, label_pos[1] - length, label_pos[0] + width/2, label_pos[1])
    elif text_orient == "bottom" or text_orient == "down":
        label_box = (label_pos[0] - width/2, label_pos[1], label_pos[0] + width/2, label_pos[1] + length)


    overlap_list = check_box_overlap_error(label_box, "Global Label", label_ref, label_pos[0], label_pos[1])
    if overlap_list:
        if RAISE_ERR_FLAG:
            raise ValueError(f"Global label '{label_text}' at position {label_pos} overlaps with existing symbols: {overlap_list}")
        else:
            print(f"Warning: Global label '{label_text}' at position {label_pos} overlaps with existing symbols: {overlap_list}")


    # Initialize the coord_to_block dictionary for labels
    if tuple(label_pos) not in coord_to_block:
        coord_to_block[tuple([round(label_pos[0], 2), round(label_pos[1], 2)])] = {
            "block_x": [],
            "block_y": [],
            "position": "Label"
        }
    else:
        coord_to_block[tuple([round(label_pos[0], 2), round(label_pos[1], 2)])]["position"] = "Label"


def get_global_label_location(label_val: str):
    """
    Get the list of locations of all global labels matching certain label text in the schematic.
    
    Args:
        label_val (str): The value string of the label.
    """
    schematic = load_schematic(sch_filename)

    # Find the label by reference name
    label_matches = schematic.global_label.value_matches(label_val)

    if len(label_matches) == 0:
        # print(f"Error: Label {label_val} not found in the schematic.")
        if RAISE_ERR_FLAG:
            raise ValueError(f"Label {label_val} not found in the schematic.")
        else:
            return None
    else:
        label_loc_list = []
        # Iterate through all matching labels and get their locations
        for label in label_matches:
            label_pos = label.at.value[:2]  # Get the location of the label without the rotation

            if REVERSE_Y_FLAG:
                label_pos = label_pos.copy()  # Create a copy to avoid modifying the original list
                label_pos[1] = reY(label_pos[1])  # Reverse the Y coordinate
            # append the label position to the list
            label_loc_list.append(label_pos)
        
        return label_loc_list
    

def move_global_label(label_txt: str, dx: float, dy: float, rotation: int = 0):
    """
    Move a global label in the schematic by dx, dy and rotation.

    Args:
        label_txt (str): The text of the label to move.
        dx (float): The distance to move in the x direction.
        dy (float): The distance to move in the y direction.
        rotation (int): The rotation angle in degrees.
    """

    if REVERSE_Y_FLAG:
        dy = -dy

    schematic = load_schematic(sch_filename)

    # Find the global label by value
    label = schematic.global_label.value_matches(label_txt)[0]

    # Get the current location
    x, y, rot = label.at.value

    # Set the new location
    label.move(align_to_grid(x + dx), align_to_grid(y + dy), rot + rotation)

    # Save the schematic
    save_schematic(schematic, sch_filename)


def add_net_label(label_pos: list, label_text: str):
    """
    Add a net label to the schematic. 

    Args:
        label_pos (tuple): The position of the label (x, y).
        label_text (str): The text of the label.
    """

    if REVERSE_Y_FLAG:
        label_pos = label_pos.copy()  # Create a copy to avoid modifying the original list
        label_pos[1] = reY(label_pos[1])

    schematic = load_schematic(sch_filename)

    # Add the net label to the schematic
    net_label = schematic.label.new()
    net_label.move(align_to_grid(label_pos[0]), align_to_grid(label_pos[1]))
    net_label.value = label_text

    # Save the schematic
    save_schematic(schematic, sch_filename)

    # Check for position overlap error
    check_position_overlap_error("Net Label", label_text, label_pos[0], label_pos[1])


def get_net_label_location(label_val: str):
    """
    Get the list of locations for all net labels matching the given name in the schematic.
    
    Args:
        label_val (str): The value string of the label.
    """

    schematic = load_schematic(sch_filename)

    # Find the label by reference name
    label_matches = schematic.label.value_matches(label_val)

    if len(label_matches) == 0:
        # print(f"Error: Net Label {label_val} not found in the schematic.")
        raise ValueError(f"Net Label {label_val} not found in the schematic.") 
    else:
        label_loc_list = []
        # Iterate through all matching labels and get their locations
        for label in label_matches:
            label_pos = label.at.value[:2]  # Get the location of the label without the rotation

            if REVERSE_Y_FLAG:
                label_pos = label_pos.copy()  # Create a copy to avoid modifying the original list
                label_pos[1] = reY(label_pos[1])  # Reverse the Y coordinate
            # append the label position to the list
            label_loc_list.append(label_pos)
        
        return label_loc_list



def add_new_wire(start_pos: list, end_pos: list, reY_off: bool = False, allow_diagonal: bool = False) -> list | None:
    """
    Add a new wire to the schematic. First check whether the wire already exists. 
    Then whether it overlaps with existing wires. 
    If overlapping with another wire and one end of the two wires are the same, then we need to create a junction and break up the wire.

    Args:
        schematic (skip.Schematic): The schematic object.
        start_pos (tuple): The starting position of the wire (x, y).
        end_pos (tuple): The ending position of the wire (x, y).
        reY_off (bool): If True, do not reverse the Y coordinate. Default is False.
    """
    
    if isinstance(start_pos, tuple):
        start_pos = list(start_pos)
    if isinstance(end_pos, tuple):
        end_pos = list(end_pos)


    if REVERSE_Y_FLAG and not reY_off:
        start_pos = start_pos.copy()  # Create a copy to avoid modifying the original list
        end_pos = end_pos.copy()
        start_pos[1] = reY(start_pos[1])
        end_pos[1] = reY(end_pos[1])

    x_range = [0, 300] # Unit: mm
    y_range = [0, 200]

    # if max(start_pos[0], end_pos[0]) > x_range[1] or min(start_pos[0], end_pos[0]) < x_range[0]:
    #     print("Error: X coordinate out of range. Skip adding a new wire.")
    #     return
    # if max(start_pos[1], end_pos[1]) > y_range[1] or min(start_pos[1], end_pos[1]) < y_range[0]:
    #     print("Error: Y coordinate out of range. Skip adding a new wire.")
    #     return
    
    # Align the positions to the grid
    # The grid size is 1.27mm, so we align the positions to the nearest 1.27mm
    start_pos = [align_to_grid(start_pos[0]), align_to_grid(start_pos[1])]
    end_pos = [align_to_grid(end_pos[0]), align_to_grid(end_pos[1])]


    # add_new_wire() only accept horizontal or vertical wires for instant write-out.
    if (start_pos[0] != end_pos[0] and start_pos[1] != end_pos[1]) and not allow_diagonal:
        print("Error: The wire must be a straight line, either horizontal or vertical. Skip adding a new wire.")
        print(f"Start position: {start_pos}, End position: {end_pos}")
        # This error raise is ok, because current logic should ensure only straight wires are passed to this function.
        raise ValueError("The wire must be a straight line, either horizontal or vertical. Skip adding a new wire.")

    
    # If the wire is a straight line, we record the direct connection in the direct_connections dictionary.
    # And then, we write out the wire to schematic file after this line.
    add_point_connection(start_pos, end_pos, direct_connections)
    
    # Load the schematic
    schematic = load_schematic(sch_filename)

    # Check if the wire already exists
    for wire in schematic.wire:
        if wire.start.value == start_pos and wire.end.value == end_pos:
            print("Warning: Wire already exists. Skip adding a new wire.")
            return



    # If the wire overlaps with another wire and has a common end, we need to create a junction and break up the wire.
    for wire in schematic.wire:
        flag, junction = check_line_duplicate([start_pos, end_pos], [wire.start.value, wire.end.value])
        if flag == True:
            # add_junction() function below are meant for LLM-based code operation, so we need to turn off "reverse the Y coordinate" so that coordinates are consistent.
            # Add a junction at the overlapping point
            add_junction(junction, reY_off=True)
            # If a junction is created, add it to the block mapping.
            coord_to_block[tuple([round(junction[0], 2), round(junction[1], 2)])] = {
                "block_x": [],
                "block_y": [],
                "position": "Junction"
            }
            schematic = load_schematic(sch_filename)

    # # Finally, add the new wire to the schematic
    # wire = schematic.wire.new()
    # wire.start.value = start_pos
    # wire.end.value = end_pos

    # wire.stroke.width.value = 0.25 # Set the wire default width to 0.5mm

    # # Save the schematic
    # save_schematic(schematic, sch_filename)

    append_kicad_wire_raw(sch_filename, start_pos, end_pos)

def check_wire_overlap(start_pos: list, end_pos: list):
    """
    Helper function to check if a wire overlaps with existing wires in the schematic.
    """

    x1 = min(start_pos[0], end_pos[0])
    x2 = max(start_pos[0], end_pos[0])
    y1 = min(start_pos[1], end_pos[1])
    y2 = max(start_pos[1], end_pos[1])
    overlap_list = check_box_overlap_error((x1, y1, x2, y2), "Wire", f"[{start_pos[0]:.3f}, {(start_pos[1]):.3f}] -> [{end_pos[0]:.3f}, {(end_pos[1]):.3f}]", (x1+x2)/2,  (y1+y2)/2,
                                           auto_route_try= True)
    return overlap_list


def add_auto_wire(start_pos: list, end_pos: list, reY_off: bool = False):
    """
    Add a new wire to the schematic, and automatically route it if it overlaps with existing wires.
    
    Args:
        start_pos (tuple): The starting position of the wire (x, y).
        end_pos (tuple): The ending position of the wire (x, y).
        reY_off (bool): If True, do not reverse the Y coordinate. Default is False.
    """
    if isinstance(start_pos, tuple):
        start_pos = list(start_pos)
    if isinstance(end_pos, tuple):
        end_pos = list(end_pos)


    if REVERSE_Y_FLAG and not reY_off:
        start_pos = start_pos.copy()  # Create a copy to avoid modifying the original list
        end_pos = end_pos.copy()
        start_pos[1] = reY(start_pos[1])
        end_pos[1] = reY(end_pos[1])

    x_range = [0, 300] # Unit: mm
    y_range = [0, 200]

    # if max(start_pos[0], end_pos[0]) > x_range[1] or min(start_pos[0], end_pos[0]) < x_range[0]:
    #     raise ValueError("Error: X coordinate out of range. Skip adding a new wire.")

    # if max(start_pos[1], end_pos[1]) > y_range[1] or min(start_pos[1], end_pos[1]) < y_range[0]:
    #     raise ValueError("Error: Y coordinate out of range. Skip adding a new wire.")
    
    # Align the positions to the grid
    # The grid size is 1.27mm, so we align the positions to the nearest 1.27mm
    start_pos = [align_to_grid(start_pos[0]), align_to_grid(start_pos[1])]
    end_pos = [align_to_grid(end_pos[0]), align_to_grid(end_pos[1])]


    # add_new_wire() only accept horizontal or vertical wires for instant write-out.
    if start_pos[0] != end_pos[0] and start_pos[1] != end_pos[1]:
        raise ValueError(f"Error: The wire must be a straight line, either horizontal or vertical. Skip adding a new wire. Start position: {start_pos}, End position: {end_pos}")
        # This error raise is ok, because current logic should ensure only straight wires are passed to this function.

    
    ### NOTE: Put the error check before file writing so that we can handle auto-routing.
    # Check if the wire overlaps with existing symbols.
    overlap_list = check_wire_overlap(start_pos, end_pos)

    if overlap_list is None:
        # If no overlap, then the wire is added successfully.
        add_new_wire(start_pos, end_pos, reY_off=True)
        return True
    else:
        # If there is an overlap, we need to auto-route the wire.
        print(f"Auto-routing wire from {start_pos} to {end_pos} due to overlap with existing wires: {overlap_list}")
        
        shift_unit = 1.27  # Unit: mm, the minimum shift unit for auto-routing
        max_shift = 5 * shift_unit  # Maximum shift distance for auto-routing, e.g. 10mm
        current_shift = 0  # Current shift distance
        while overlap_list and abs(current_shift) <= max_shift:
            # Try to shift the wire by current_shift in both x and y directions
            # Increase the shift distance for the next iteration
            current_shift += shift_unit  
            
            # To keep the start and end points the same, we need to create 3 wire segments.
            # All three segments should not overlap with existing wires.
            # If the current wire is along X axis, we shift it along Y axis, and vice versa.
            for test_shift in [current_shift, -current_shift]:
                if start_pos[0] == end_pos[0]:  # Vertical wire
                    # Shift the wire along X axis
                    corner_pos1 = [start_pos[0] + test_shift, start_pos[1]]
                    corner_pos2 = [end_pos[0] + test_shift, end_pos[1]]

                    if check_wire_overlap(start_pos, corner_pos1) is None and check_wire_overlap(corner_pos1, corner_pos2) is None and check_wire_overlap(corner_pos2, end_pos) is None:
                        # If no overlap, then the wire is routed successfully.
                        add_new_wire(start_pos, corner_pos1, reY_off=True)
                        add_new_wire(corner_pos1, corner_pos2, reY_off=True)
                        add_new_wire(corner_pos2, end_pos, reY_off=True)
                        return True
                else:  # Horizontal wire
                    # Shift the wire along Y axis
                    corner_pos1 = [start_pos[0], start_pos[1] + test_shift]
                    corner_pos2 = [end_pos[0], end_pos[1] + test_shift]
                    if check_wire_overlap(start_pos, corner_pos1) is None and check_wire_overlap(corner_pos1, corner_pos2) is None and check_wire_overlap(corner_pos2, end_pos) is None:
                        # If no overlap, then the wire is routed successfully.
                        add_new_wire(start_pos, corner_pos1, reY_off=True)
                        add_new_wire(corner_pos1, corner_pos2, reY_off=True)
                        add_new_wire(corner_pos2, end_pos, reY_off=True)
                        return True
            
            
        # If we reach here, it means we cannot route the wire within the maximum shift distance.
        # if RAISE_ERR_FLAG:
        #     raise ValueError(f"Error: Cannot route wire from {start_pos} to {end_pos} due to overlap with existing wires: {overlap_list}. Maximum shift distance reached.")
        # else:
        #     print(f"Error: Cannot route wire from {start_pos} to {end_pos} due to overlap with existing wires: {overlap_list}. Maximum shift distance reached.")
        #     return False

        # directly add a non-straight wire to the schematic.
        print(f"Warning: Cannot route wire from {start_pos} to {end_pos} due to overlap with existing wires: {overlap_list}. Adding a direct or diagonal wire instead.")
        # Add a non-straight wire to the schematic
        add_new_wire(start_pos, end_pos, reY_off=True, allow_diagonal=True) # Allow diagonal wires to be added if auto-routing fails.
        return True


def get_pin_location(symbol_ref: str, pin_name: str):
    """
    Get the location of a pin in the schematic.
    
    Args:
        symbol_ref (str): The reference of the symbol.
        pin_ref (str): The reference of the pin.
    """

    # If this is label ref, get label poistion by refence
    if is_label_ref(symbol_ref, pin_name):
        return get_label_location_byRef(symbol_ref, pin_name)

    schematic = load_schematic(sch_filename)

    # Find the symbol by reference name
    sym_match = schematic.symbol.reference_matches(symbol_ref)
    if len(sym_match) == 0:
        # print(f"Error: Symbol {symbol_ref} not found in the schematic.")
        raise ValueError(f"Symbol {symbol_ref} not found in the schematic.")
    
    symbol = sym_match[0]
    # assert len(sym_match)==1, "Error: Found multiple symbol matches, should be exactly one match only!"

    # if '/' in pin_ref:
    #     pin_ref = pin_ref.replace('/', '{slash}')  # Replace '/' with '{slash}' to match the pin name in the schematic

    if '{slash}' in pin_name:
        pin_name = pin_name.replace('{slash}', '/')  # Replace '{slash}' back to '/' for matching the pin name in the schematic

    pin_instance = None
    if isinstance(symbol.pin, my_skip_lib.eeschema.schematic.symbol.SymbolPin) or isinstance(symbol.pin, my_skip_lib.sexp.parser.ParsedValue):
        # If the symbol.pin is a valid pin already, like for power symbols, then we can directly use it.
        pin_instance = symbol.pin
    elif isinstance(symbol.pin, my_skip_lib.eeschema.schematic.symbol.SymbolPinCollection):
        # Why?
        for p in symbol.pin:
            if p.number == pin_name or p.name == pin_name:
                pin_instance = p
        if pin_instance is None:
            print(f"Warning: Pin {pin_name} not found in symbol {symbol_ref} by number or name. Trying to find the best match.")
            pin_instance = find_best_pin_instance(symbol, pin_name)
    elif pin_name in symbol.pin:
        # If the pin_name is a valid pin name in the symbol
        pin_instance = symbol.pin[pin_name]
    elif 'n'+pin_name in symbol.pin:
        # If the pin_name is a valid pin name in the symbol with 'n' prefix
        pin_instance = symbol.pin['n'+pin_name]
    elif 'Pin_' + pin_name in symbol.pin:
        # If the pin_name is a valid pin name in the symbol with 'Pin_' prefix
        pin_instance = symbol.pin['Pin_' + pin_name]
    else:
        # May be other strange transformation for names. We directly check the name of all pins.
        pin_instance = None
        for p in symbol.pin:
            if p.name == pin_name:
                pin_instance = p
                break
        if pin_instance is None:
            pin_instance = find_best_pin_instance(symbol, pin_name)

    if pin_instance is None:
        raise ValueError(f"Pin {pin_name} not found in symbol {symbol_ref}. Available pins: {list(symbol.pin)}")
    
    if isinstance(pin_instance, my_skip_lib.eeschema.schematic.symbol.SymbolPin):
        pin_pos = pin_instance.location.value[:2] # Get the location of the pin without the rotation
    elif isinstance(pin_instance, my_skip_lib.sexp.parser.ParsedValue):
        pin_pos = pin_instance.parent.at.value[:2]
    else:
        raise ValueError(f"Invalid pin type. Must be a SymbolPin or Pin. But got {pin_instance} for {symbol_ref}.{pin_name}.")


    if REVERSE_Y_FLAG:
        pin_pos = pin_pos.copy()
        pin_pos[1] = reY(pin_pos[1])

    # print(f"Pin {pin_name} of symbol {symbol_ref} is located at {pin_pos}.")

    return list(pin_pos)

def get_label_location(label_text: str):

    """
    Get the location list for labels matching a label text string in the schematic. Can be either a net label or a global label.
    
    Args:
        label_text (str): The text of the label.
    """
    # try global label first
    global_label_loc_list = get_global_label_location(label_text)

    net_label_loc_list = get_net_label_location(label_text)

    if global_label_loc_list is None and net_label_loc_list is None:
        return None
    elif global_label_loc_list is None:
        return net_label_loc_list
    elif net_label_loc_list is None:
        return global_label_loc_list
    else:
        # If both global and net labels are found, return a combined list
        # This is useful for cases where the same label is used in both global and net contexts
        # e.g. "VCC" can be a global label for power supply and also a net label for a specific connection.
        return global_label_loc_list + net_label_loc_list


def get_symbol_location(symbol_ref: str):
    """
    Get the location of a symbol in the schematic.
    
    Args:
        symbol_ref (str): The reference of the symbol.
    """
    schematic = load_schematic(sch_filename)

    # Find the symbol by reference name
    sym_match = schematic.symbol.reference_matches(symbol_ref)
    if len(sym_match) == 0:
        print(f"Error: Symbol {symbol_ref} not found in the schematic.")
        if RAISE_ERR_FLAG:
            raise ValueError(f"Symbol {symbol_ref} not found in the schematic.")
        else:
            raise ValueError(f"Symbol {symbol_ref} not found in the schematic.")
    
    symbol = sym_match[0]
    assert len(sym_match)==1, "Error: Found multiple symbol matches, should be exactly one match only!"


    if REVERSE_Y_FLAG:
        return [symbol.at.value[0], reY(symbol.at.value[1])]
    else:
        return [symbol.at.value[0], symbol.at.value[1]]
    return [symbol.at.value[0], symbol.at.value[1]]


def get_symbol_mirror(symbol_ref: str):
    """
    Get the mirror direction of a symbol in the schematic.
    
    Args:
        symbol_ref (str): The reference of the symbol.
    """
    schematic = load_schematic(sch_filename)

    # Find the symbol by reference name
    sym_match = schematic.symbol.reference_matches(symbol_ref)
    if len(sym_match) == 0:
        print(f"Error: Symbol {symbol_ref} not found in the schematic.")
        if RAISE_ERR_FLAG:
            raise ValueError(f"Symbol {symbol_ref} not found in the schematic.")
        else:
            return None
    
    symbol = sym_match[0]
    assert len(sym_match)==1, "Error: Found multiple symbol matches, should be exactly one match only!"

    return symbol.mirror.value if hasattr(symbol.mirror, 'value') else None

# Give up using kiutils because it lacks support for kicad v8, v9 format differences about hiding various pins and name.
# from kiutils.schematic import Schematic, Connection, Position

def draw_manhattan_wire(start_pos: tuple, end_pos: tuple, bent_down: bool = True):
    """
    Draw a manhattan-style wire between two points in the schematic. If not a direct connection along one axis, we create a two-segment wire, with adjustable bent direction.

    Args:
        start_pos (tuple): The starting position of the wire (x, y).
        end_pos (tuple): The ending position of the wire (x, y).
        bent_down (bool): If True, the manhattan wire will be bent down. If False, it will bent upward.
    """
    # schematic = load_schematic(sch_filename)


    if start_pos[0] == end_pos[0] or start_pos[1] == end_pos[1]:
        # if the start and end positions are along the same axis, then we can directly add a wire.
        add_new_wire(start_pos, end_pos)
        return

    rstart_pos = start_pos.copy()
    rend_pos = end_pos.copy()
    # Check if start_pos and end_pos are in coord_to_block, if not, reverse the Y coordinate.
    # This is to ensure that the wire is drawn in the correct direction in the schematic.
    if REVERSE_Y_FLAG:
        if tuple(start_pos) not in coord_to_block:
            rstart_pos = [start_pos[0], reY(start_pos[1])]
        if tuple(end_pos) not in coord_to_block:
            rend_pos = [end_pos[0], reY(end_pos[1])]
        
    higher_y = min(start_pos[1], end_pos[1]) # smaller Y leads to higher position in the schematic because of the Y axis direction
    corner_x = end_pos[0] if higher_y == start_pos[1] else start_pos[0] # this is the x coordinate of the corner

    # # Check if the corner point is blocked by connected symbols.
    # if corner_x in coord_to_block[(round(rstart_pos[0], 2), round(rstart_pos[1], 2))]["block_x"] or higher_y in coord_to_block[(round(rstart_pos[0], 2), round(rstart_pos[1], 2))]["block_y"] \
    #     or corner_x in coord_to_block[(round(rend_pos[0], 2), round(rend_pos[1], 2))]["block_x"] or higher_y in coord_to_block[(round(rend_pos[0], 2), round(rend_pos[1], 2))]["block_y"]:
    #     # If the corner point is blocked by connected symbols, bent up instead.
    #     bent_down = False
    # # If bent up, the corner point always takes the larger Y coordinate -- lower Y position.
    # lower_y = max(start_pos[1], end_pos[1])
    # corner_x = end_pos[0] if lower_y == start_pos[1] else start_pos[0]
    # if corner_x in coord_to_block[(round(rstart_pos[0], 2), round(rstart_pos[1], 2))]["block_x"] or lower_y in coord_to_block[(round(rstart_pos[0], 2), round(rstart_pos[1], 2))]["block_y"] \
    #     or corner_x in coord_to_block[(round(rend_pos[0], 2), round(rend_pos[1], 2))]["block_x"] or lower_y in coord_to_block[(round(rend_pos[0], 2), round(rend_pos[1], 2))]["block_y"]:
    #     # If the corner point is blocked by connected symbols, bent down instead.
    #     bent_down = True


    # If bent down, then we go along 
    if (bent_down):
        higher_y = min(start_pos[1], end_pos[1]) # smaller Y leads to higher position in the schematic because of the Y axis direction
        corner_x = end_pos[0] if higher_y == start_pos[1] else start_pos[0] # this is the x coordinate of the corner
        # Add two wire segments
        add_auto_wire([start_pos[0], start_pos[1]], [corner_x, higher_y])
        add_auto_wire([end_pos[0], end_pos[1]], [corner_x, higher_y])
        add_junction([corner_x, higher_y])  # Add a junction at the corner point

    else:
        # If bent up, the corner point always takes the larger Y coordinate -- lower Y position.
        lower_y = max(start_pos[1], end_pos[1])
        corner_x = end_pos[0] if lower_y == start_pos[1] else start_pos[0]
        # Add two wire segments
        add_auto_wire([start_pos[0], start_pos[1]], [corner_x, lower_y])
        add_auto_wire([end_pos[0], end_pos[1]], [corner_x, lower_y])
        add_junction([corner_x, lower_y])  # Add a junction at the corner point


def is_label_ref(sym: str, pin: str):
    if f"{sym}_{pin}" in sch_label_map:
        return True
    elif f"{sym}" in sch_label_map:
        return True
    else:
        return False

def get_label_location_byRef(sym: str, pin: str):
    """
    Get the location of a label in the schematic by its reference name.
    
    Args:
        label_ref (str): The reference name of the label.
    """

    if is_label_ref(sym, pin):
        return sch_label_map[f"{sym}_{pin}"] if f"{sym}_{pin}" in sch_label_map else sch_label_map[f"{sym}"]
    else:
        raise ValueError(f"Label reference {sym} and pin {pin} not found in the schematic label map.")
    


def connect_pins(sym_a: str, pin_a: str, sym_b: str, pin_b: str):
    """Create a connection between *sym_a.pin_a* and *sym_b.pin_b*."""

    start_pos = get_pin_location(sym_a, pin_a)

    end_pos = get_pin_location(sym_b, pin_b)

    # draw_manhattan_wire(start_pos, end_pos, bent_down=bent_down)

    connect_two_points(start_pos, end_pos)


def connect_two_points(start_pos: list, end_pos: list):
    """
    Connect two points on the schematic. Will do some form of auto routing if the two points are not directly connected.
    """

    if REVERSE_Y_FLAG:
        start_pos = start_pos.copy()  # Create a copy to avoid modifying the original list
        end_pos = end_pos.copy()
        start_pos[1] = reY(start_pos[1])
        end_pos[1] = reY(end_pos[1])

    if start_pos[0] != end_pos[0] and start_pos[1] != end_pos[1]:
        ## If not a straight wire, add the points to the junction connections for later processing.
        # -- Eventually, calls draw_manhattan_wire(), which still calls add_new_wire() to write out the wires.
        add_point_connection(start_pos, end_pos, junction_connections)
        # print(f"Added non-direct connection for later write-out. {start_pos} -- {end_pos}")
        return
    else:
        # add_new_wire() now only handles direct wires.
        add_auto_wire(start_pos, end_pos, reY_off=True)  # reY_off=True to avoid reversing the Y coordinate again, since we already did it here.


connected_pins = set()

# === Auto-insert junctions between pins ===
def connect_pins_with_junctions(x, y):
    # Find the target points that should connect with (x, y)
    target_list = list(junction_connections[(x, y)])

    # Enumerate all pairs of points in target_list
    for i in range(len(target_list)):
        p1 = target_list[i]
        for j in range(i + 1, len(target_list)):
            p2 = target_list[j]

            # If the two points already directly connect, we can add a junction point in the middle.
            if p2 in direct_connections.get(p1, set()) and p1 in direct_connections.get(p2, set()):
                if p1[0] == p2[0]:  # Vertical
                    if y >= min(p1[1], p2[1]) and y <= max(p1[1], p2[1]):
                        jx = p1[0]
                        jy = y
                    else:
                        jx, jy = midpoint(p1, p2)
                elif p1[1] == p2[1]:  # Horizontal
                    if x >= min(p1[0], p2[0]) and x <= max(p1[0], p2[0]):
                        jx = x
                        jy = p1[1]
                    else:
                        jx, jy = midpoint(p1, p2)
                else:
                    assert False, "Unexpected case: p1 and p2 should be either vertical or horizontal aligned."


                if REVERSE_Y_FLAG:
                    # add and draw functions below are meant for LLM-based code operation, so we need to reverse the Y coordinate so that coordinates are consistent.
                    jy = reY(jy)
                    # Reverse the Y coordinate only for drawing
                    sy = reY(y)

                # Mark these points as connected
                connected_pins.add(frozenset([tuple(p1), tuple(p2)]))  # frozen set to allow orderless
                connected_pins.add(frozenset([tuple([x, y]), tuple(p1)]))
                connected_pins.add(frozenset([tuple([x, y]), tuple(p2)]))
                
                # Add new junction point
                add_junction([jx, jy])
                coord_to_block[(round(jx, 2), round(jy, 2))] = {
                    "block_x": [],
                    "block_y": [],
                    "position": "Junction"
                }

                # Draw the manhattan wire between (x, y) and the junction point
                if (jx - x) * (jy - sy) > 0:
                    # If the wire is bent down, we draw it bent down.
                    bent_down = True
                else:
                    bent_down = False
                
                if p1[0] == p2[0]:  # Vertical
                    # Block the x-axis
                    coord_to_block[(round(jx, 2), round(jy, 2))]["block_x"].append(p1[0])
                    try:
                        draw_manhattan_wire(start_pos=[x, sy], end_pos=[jx, jy], bent_down=bent_down)
                    except:
                        draw_manhattan_wire(start_pos=[x, sy], end_pos=[jx, jy], bent_down=not bent_down)
                elif p1[1] == p2[1]:  # Horizontal
                    # Block the y-axis
                    coord_to_block[(round(jx, 2), round(jy, 2))]["block_y"].append(p1[1])
                    try:
                        draw_manhattan_wire(start_pos=[x, sy], end_pos=[jx, jy], bent_down=bent_down)
                    except:
                        draw_manhattan_wire(start_pos=[x, sy], end_pos=[jx, jy], bent_down=not bent_down)


def connect_bent_wires(x, y):
    target_list = list(junction_connections[(x, y)])
    for i in range(len(target_list)):
        p1 = target_list[i]

        # If there are points not yet connected to (x, y), we need to connect them with a single L-shape bent wire.
        if frozenset([tuple([x,y]), tuple(p1)]) not in connected_pins:
            # Connect them with a manhattan wire.
            if (x-p1[0]) * (y-p1[1]) > 0:
                bent_down = False
            else:
                bent_down = True

            # Mark these points as connected
            connected_pins.add(frozenset([tuple([x,y]), tuple(p1)]))

            if REVERSE_Y_FLAG:
                # add and draw functions below are meant for LLM-based code operation, so we need to reverse the Y coordinate so that coordinates are consistent.
                sy = reY(y)
                sp1 = reY(p1[1])

            if (x - p1[0]) * (y - sp1) > 0:
                # If the wire is bent down, we draw it bent down.
                bent_down = True
            else:
                bent_down = False

            try:
                draw_manhattan_wire(start_pos=[x, sy], end_pos=[p1[0], sp1], bent_down=bent_down)
            except:
                draw_manhattan_wire(start_pos=[x, sy], end_pos=[p1[0], sp1], bent_down=not bent_down)



def write_out_all_wires():

    '''Write out all wires in the schematic.'''

    # Check all points for junctions
    for point in junction_connections:
        connect_pins_with_junctions(point[0], point[1])
    
    # Connecting pins with bent wires
    for point in junction_connections:
        connect_bent_wires(point[0], point[1])

'''
Below are KiCad footprint matching and normalization functions, which are used for the symbol-to-footprint mapping in the PCB layout stage.
'''

from difflib import SequenceMatcher

# ---- Defaults you required ----
DEFAULT_MAP_RCL = {
    'R': 'Resistor_SMD:R_0201_0603Metric',
    'C': 'Capacitor_SMD:C_0201_0603Metric',
    'L': 'Inductor_SMD:L_0201_0603Metric',
    'Q': "Package_TO_SOT_SMD:SOT-1123",
}

def _norm(s: str) -> str:
    """Normalize text for fuzzy matching."""
    if not s:
        return ''
    s = s.lower()
    s = re.sub(r'[^a-z0-9_+\-\s\.]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _is_smd(fp_entry: dict) -> bool:
    """
    Heuristic to decide if a footprint is SMD.
    We check library nickname, footprint name, tags, descr, and 'attr' flags.
    """
    lib = fp_entry.get('lib', '')
    name = fp_entry.get('name', '')
    descr = fp_entry.get('descr', '')
    tags = fp_entry.get('tags', '')
    attr = fp_entry.get('attr', []) or []

    blob = ' '.join([
        lib, name, descr, tags, ' '.join(attr)
    ]).lower()

    # Common signals for SMD
    hints = ['smd', '_smd', 'qfn', 'qfp', 'sot', 'soic', 'tssop', 'dfn', 'lga', 'bga', 'lqfp', 'mlf']
    if any(h in blob for h in hints):
        return True
    # Through-hole signals
    th_hints = ['tht', 'dip', 'to-220', 'to220', 'dil', 'pin_header', 'pinheader', 'axial']
    if any(h in blob for h in th_hints):
        return False
    # Fallback: prefer SMD in doubt
    return True

def _flatten_fp_lib(fp_lib: dict) -> list:
    """
    Flatten: {lib: [ {name, descr, tags, attr, ...}, ...]} -> 
    [ {lib, name, descr, tags, attr, full}, ... ]
    """
    out = []
    for lib, items in (fp_lib or {}).items():
        for it in items:
            out.append({
                'lib': lib,
                'name': it.get('name', ''),
                'descr': it.get('descr', '') or it.get('description', ''),
                'tags': it.get('tags', ''),
                'attr': it.get('attr', []),
                'full': f"{lib}:{it.get('name','')}"
            })
    return out

_ARRAY_RE = re.compile(r'\b0*(\d+)\s*x\s*0*(\d+)\b', re.I)

def _extract_array_spec(desc: str) -> tuple[int | None, int | None, str | None]:
    """
    Extract array spec like '01x04' from description, normalize to '1x04'.
    Also honor 'single row' / 'dual row' hints:
      - 'single row' -> rows=1
      - 'dual row'/'double row' -> rows=2 (if not explicitly given)
    Returns (rows, cols, normalized_token) where normalized_token is like '1x04'.
    """
    if not desc:
        return None, None, None

    d = desc.lower()
    rows_hint = None
    if 'single row' in d or '1-row' in d or 'one row' in d:
        rows_hint = 1
    elif 'dual row' in d or 'double row' in d or '2-row' in d or 'two row' in d:
        rows_hint = 2

    m = _ARRAY_RE.search(d)
    if not m:
        # If no explicit NxM, still return row hint (e.g., single row) with None cols
        return rows_hint, None, None

    a, b = int(m.group(1)), int(m.group(2))
    # If 'single row' is stated, normalize to rows=1, cols=max(a,b)
    if rows_hint == 1:
        rows, cols = 1, max(a, b)
    else:
        rows, cols = a, b

    norm_token = f'{rows}x{cols:02d}' if cols is not None else None
    return rows, cols, norm_token

# --- NEW: lightweight semantic synonym map ---
# key -> set of synonyms / hyponyms
SEMANTIC_MAP = {
    'connector': {
        'connector', 'conn', 'header', 'pinheader', 'pin header', 'pin-header',
        'socket', 'receptacle', 'terminal', 'terminal block', 'screw terminal',
        'jst', 'molex', 'ph', 'xh', 'sh', 'dupont', 'hdr'
    },
    'resistor': {'resistor', 'res', 'r'},
    'capacitor': {'capacitor', 'cap', 'c', 'ceramic', 'electrolytic', 'mlcc'},
    'inductor': {'inductor', 'ind', 'l', 'choke'},
    'diode': {'diode', 'led', 'schottky', 'tvS', 'esd', 'rectifier'},
    'transistor': {'transistor', 'bjt', 'mosfet', 'fet', 'sofet'},
    'opamp': {'opamp', 'op-amp', 'operational amplifier', 'amplifier'},
}

def _semantic_tokens(text: str) -> set[str]:
    """Extract coarse semantic tokens using SEMANTIC_MAP."""
    if not text:
        return set()
    t = (text or '').lower()
    toks = set()
    for canon, aliases in SEMANTIC_MAP.items():
        if any(a in t for a in aliases):
            toks.add(canon)
    return toks

def _score_fp(desc: str, fp: dict, prefer_smd: bool = True) -> float:
    """
    Fuzzy score with:
      - difflib similarity on name/descr/tags
      - keyword bonuses
      - strict array token bonus (e.g., 1x04 with word boundaries)
      - SMD preference
      - NEW: semantic overlap bonus (e.g., 'connector' matches 'pin header')
    """
    d = _norm(desc)
    name  = _norm(fp.get('name', ''))
    descr = _norm(fp.get('descr', ''))
    tags  = _norm(fp.get('tags', ''))

    # base similarity
    r_name  = SequenceMatcher(None, d, name).ratio()
    r_descr = SequenceMatcher(None, d, descr).ratio()
    r_tags  = SequenceMatcher(None, d, tags).ratio()
    base = max(r_name, r_descr, r_tags)

    bonus = 0.0

    # lightweight keywords (keep your old ones)
    kw_blob_src = (desc or '').lower()
    kw_blob_fp  = (' '.join([fp.get('name',''), fp.get('descr','') or '', fp.get('tags','') or ''])).lower()

    # --- NEW: semantic overlap bonus ---
    src_sem = _semantic_tokens(kw_blob_src)
    fp_sem  = _semantic_tokens(kw_blob_fp)
    if src_sem and fp_sem:
        inter = src_sem & fp_sem
        if inter:
            # Clear semantic agreement (e.g., 'connector' ↔ 'pin header')
            bonus += 0.15
        else:
            # Weak hint: share broader electromech domain terms
            # e.g., source says 'connector', fp mentions 'socket' -> still counted above;
            # here we add a tiny nudge if both sides have *some* semantic class
            bonus += 0.03

    # array spec bonus (strict boundary to avoid 1x40 vs 1x04)
    rows, cols, tok = _extract_array_spec(desc or '')
    if tok:
        tok_re = re.compile(rf'\b{re.escape(tok)}\b', re.I)
        if tok_re.search(fp.get('name','')) or tok_re.search(fp.get('descr','') or '') or tok_re.search(fp.get('tags','') or ''):
            bonus += 0.12

    # prefer SMD
    if prefer_smd:
        bonus += 0.10 if _is_smd(fp) else -0.05

    return base + bonus

def _pick_fp_by_description(desc: str, fp_lib: dict, prefer_smd: bool = True) -> str | None:
    """
    Pick the best footprint (Library:Name) using fuzzy/semantic matching.
    NEW: If the description indicates a connector AND includes an NxM spec,
         we ENFORCE exact pin-count match (e.g., 01x04 ↔ 1x04/01x4/…).
         If no candidate matches that spec, return None (no unsafe fallback).
    """
    flat = _flatten_fp_lib(fp_lib)
    if not flat:
        return None

    # Detect if source is a connector (semantic)
    src_sem = _semantic_tokens(desc or '')
    is_connector = ('connector' in src_sem)

    # Parse NxM from description (e.g., 'single row, 01x04' -> rows=1, cols=4)
    rows, cols, tok = _extract_array_spec(desc or '')

    # --- ENFORCEMENT: if connector & have explicit NxM, filter candidates strictly ---
    candidates = flat
    if is_connector and (rows is not None and cols is not None):
        # Extract NxM (like 1x04, 01x10, 2x5, etc.)
        m = re.search(r'\b0*(\d+)\s*x\s*0*(\d+)\b', desc)
        if not m:
            return None

        rows, cols = int(m.group(1)), int(m.group(2))

        # Normalize to "1x04" format with leading zero for col < 10
        nxm = f"{rows}x{cols:02d}"

        # Construct the default connector footprint name
        footprint = f"Connector_PinHeader_1.00mm:PinHeader_{nxm}_P1.00mm_Vertical"
        return footprint

    # Score remaining candidates as before
    scored = []
    for fp in candidates:
        s = _score_fp(desc or '', fp, prefer_smd=prefer_smd)
        scored.append((s, fp))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Keep previous “good score” logic
    top_score, top_fp = scored[0]
    if top_score >= 0.35:
        return top_fp['full']

    # Fallbacks (only among the filtered candidates)
    for _, fp in scored:
        if _is_smd(fp):
            return fp['full']
    return scored[0][1]['full'] if scored else None

def _default_fp_for_ref(ref: str) -> str | None:
    """Return forced default for R/C/L based on the reference prefix."""
    if not ref:
        return None
    prefix = ref.strip().upper()[:1]
    return DEFAULT_MAP_RCL.get(prefix)

def get_fp(sch_filename: str = sch_filename, prefer_smd: bool = True) -> dict:
    """
    Get the footprints of all symbols in the schematic.
    1) If the symbol already has a footprint, keep it.
    2) Else, try to infer by description against the parsed footprint libraries (fp_library_index).
       - Prefer SMD footprints.
       - Force defaults for R/C/L to:
           R -> Resistor_SMD:R_0201_0603Metric
           C -> Capacitor_SMD:C_0201_0603Metric
           L -> Inductor_SMD:L_0201_0603Metric
        - Force: Jumper:SolderJumper_2_Open -> Jumper:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm
       - If still not found, pick the first matched candidate.
    Return:
        { Reference -> "Library:Name" or None }
    """

    fp_library_index = load_organized_fp(Path("./export/organized_fp.json"))

    schematic = load_schematic(sch_filename)
    footprints = {}

    # Check if schematic has symbols
    if not getattr(schematic, 'symbol', None):
        print("No symbols found in the schematic.")
        return footprints

    for symbol in getattr(schematic, 'symbol', []):
        # lib_id like "Device:R" or "power:+3.3V"
        lib_id = getattr(getattr(symbol, 'lib_id', None), 'value', '') or ''
        symbol_lib, symbol_name = (lib_id.split(':', 1) + [''])[:2] if ':' in lib_id else (lib_id, '')

        # Skip power symbols
        if symbol_lib.lower() == 'power':
            continue

        if symbol_name == 'SolderJumper_2_Open' and symbol_lib == 'Jumper':
            footprints[getattr(getattr(symbol, 'property', None), 'Reference', None).value] = "Jumper:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm"
            fp   = getattr(getattr(symbol, 'property', None), 'Footprint', None)
            if fp:
                fp.value = "Jumper:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm"
            continue

        # Reference/value/description/footprint fields (defensive)
        ref  = getattr(getattr(symbol, 'property', None), 'Reference', None)
        val  = getattr(getattr(symbol, 'property', None), 'Value', None)
        desc = getattr(getattr(symbol, 'property', None), 'Description', None)
        fp   = getattr(getattr(symbol, 'property', None), 'Footprint', None)

        ref_str  = getattr(ref, 'value', '') if ref else ''
        val_str  = getattr(val, 'value', '') if val else ''
        desc_str = getattr(desc, 'value', '') if desc else ''
        fp_str   = getattr(fp,  'value', '') if fp  else ''

        # Case 1: already has a footprint
        if fp_str:
            footprints[ref_str] = fp_str
            forced = _default_fp_for_ref(ref_str)
            if forced:
                footprints[ref_str] = forced
                # also inject/update back to the symbol if your object model allows writing:
                if fp:
                    fp.value = forced
            continue

        # Case 2: forced default for R/C/L by reference prefix
        forced = _default_fp_for_ref(ref_str)
        if forced:
            footprints[ref_str] = forced
            # also inject/update back to the symbol if your object model allows writing:
            if fp:
                fp.value = forced
            continue

        # Case 3: fuzzy match by description against the provided footprint library index
        print(desc_str)
        picked = _pick_fp_by_description(desc_str or val_str or symbol_name, fp_library_index, prefer_smd=prefer_smd)
        footprints[ref_str] = picked

        # Optionally inject back to schematic symbol object
        if fp and picked:
            fp.value = picked

        # Progress logging (optional)
        sys.stdout.write(f"\rAssigned {ref_str:>6s}: {picked or 'None'}        ")
        sys.stdout.flush()

    sys.stdout.write('\r' + ' ' * 80 + '\r')
    print("Footprint assignment done.")
    schematic.write(sch_filename)
    return footprints

def example_usage():
    """
    Example usage of the functions in this module.
    """
    add_schematic_symbol(symbol_lib="RF_Module", symbol_name="ESP-WROOM-02", pos_x=150, pos_y=100, reference="U1", value="ESP-WROOM-02")

    add_schematic_symbol(symbol_lib="Device", symbol_name="R", pos_x=180, pos_y=150, reference="R1", value="10K")

    add_schematic_symbol(symbol_lib="Device", symbol_name="D", pos_x=200, pos_y=150, reference="D1", value="RED")

    connect_pins("U", "VDD", "#PWR1", "1", bent_down=False)

    connect_pins("U", "GND", "#PWR2", "1", bent_down=True)

    # Add a global label for the EN pin
    EN_pin_loc = get_pin_location("U", "EN")
    add_net_label([EN_pin_loc[0]-10, EN_pin_loc[1]], "EN")

    # Connect the EN pin to the global label
    add_new_wire(get_pin_location("U", "EN"), get_net_label_location("EN"))





## Example usage. for testing purposes only.
if __name__ == "__main__":

    # Test reading the footprints of all symbols in the schematic.
    fps = get_fp(sch_filename="")
    print(fps)