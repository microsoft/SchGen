import uuid
import copy
import re

if __name__ == "__main__":
    import sys
    # open config file to get the project path
    with open("./configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        project_path = lines[0].strip()
        sys.path.append(project_path)

from config import KICAD_SYMBOL_LIB_PATH, KICAD_FOOTPRINT_LIB_PATH


from modules.utils.misc import *

# SYMBOL_LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/"
# SYMBOL_LIB = "C:\\Program Files\\KiCad\\8.0\\share\\kicad\\symbols\\"

def parse_sexp(sexp_str):
    """
    Parse an S-expression string into a nested list structure.
    """
    # Add spaces around parentheses to ensure proper tokenization
    sexp_str = sexp_str.replace('(', ' ( ').replace(')', ' ) ')
    
    # Updated regex to properly handle spaces and quoted strings
    tokens = re.findall(r'[()]|"(?:\\.|[^"])*"|[^()\s]+', sexp_str)
    
    # Remove any empty strings from tokenization
    tokens = [t.strip() for t in tokens if t.strip()]
    
    stack = []
    for token in tokens:
        if token == '(':
            stack.append([])
        elif token == ')':
            if len(stack) > 1:
                closed = stack.pop()
                stack[-1].append(closed)
        else:
            # Handle quoted strings by removing the quotes
            # if token.startswith('"') and token.endswith('"'):
            #     token = token[1:-1].replace('\\"', '"')
            stack[-1].append(token)
    return stack[0]

def format_sexp(sexp, indent=0, indent_size=4):
    """
    Format a nested list S-expression back into a string with proper indentation.
    """
    # Handle non-list values (atoms)
    if not isinstance(sexp, list):
        # Quote strings with spaces, special characters, or empty strings
        if isinstance(sexp, str) and (any(c in sexp for c in ' ()"') or not sexp):
            # Escape any double quotes in the string
            # escaped = sexp.replace('"', '\\"')
            # return f'"{escaped}"'
            return sexp
        return str(sexp)
    
    # Handle empty lists
    if not sexp:
        return "()"
    
    # Start the formatted output
    result = []
    
    # Add opening parenthesis
    result.append("(" + format_sexp(sexp[0]))
    
    # Process remaining items with proper indentation
    for i, item in enumerate(sexp[1:], 1):
        if isinstance(item, list):
            # For nested lists, add a newline and indent
            result.append("\n" + " " * (indent + indent_size))
            result.append(format_sexp(item, indent + indent_size, indent_size))
        else:
            # For simple items, just add a space
            result.append(" " + format_sexp(item))

    # Close the expression
    if ")" in result[-1]:
        # avoid two consecutive closing parentheses
        result.append("\n" + " " * indent + ")")
    else:
        result.append(")")
    
    return "".join(result)

def read_kicad_sch(filename):
    """
    Read a KiCad schematic file and return its S-expression structure.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    return parse_sexp(content)

def write_kicad_sch(sexp, filename):
    """
    Write a KiCad schematic S-expression structure to a file.
    """
    formatted = format_sexp(sexp)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(formatted)

def  read_kicad_sym(filename):
    """
    Read a KiCad symbol library file and return its S-expression structure.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    return parse_sexp(content)

def find_lib_symbols_section(sch_sexp):
    """
    Find the lib_symbols section in a schematic file.
    """
    for i, item in enumerate(sch_sexp):
        if isinstance(item, list) and item and item[0] == 'lib_symbols':
            return i
    return None

def fix_wrong_pin_def(item):
    """
    Fix the pin definition in the symbol library.
    This function is a placeholder for any specific logic needed to fix pin definitions.
    """
    # This function can be implemented based on specific requirements

    # If we have two symbol def list, likely correct one.
    if isinstance(item[-1], list) and item[-1][0] == 'symbol' and isinstance(item[-2], list) and item[-2][0] == 'symbol':
        # print("Found two symbol definitions, likely correct one.")
        pass
    elif isinstance(item[-1], list) and item[-1][0] == 'symbol':
        # print(f"Found a single symbol definition, likely not a correct one. {item[1]}")
        symbol_def = item[-1]
        assert len(symbol_def) >= 3, "Symbol definition must have at least 3 elements: 'symbol', name, and pin definitions."
        if 'pin' not in symbol_def[2][0] and 'pin' in symbol_def[-1][0]:
            # If pin and non-pin definitions are mixed, we need to fix it.
            # print("Fixing pin definition in the symbol.")
            # 1. copy the pin defs from the end
            pin_num = 0
            while symbol_def[-pin_num-1][0] == 'pin':
                pin_num += 1
            tmp_pin_defs = symbol_def[-pin_num:].copy()  # Copy the pin definitions
            # 2. remove the pin defs from the end
            symbol_def = symbol_def[:-pin_num]
            # 3. create another symbol definition with the pin defs
            new_symbol_def = symbol_def[:2].copy()
            new_symbol_def += tmp_pin_defs  # Add the pin definitions

            # 4. append the new symbol definition to the item
            item.append(new_symbol_def)
            # print("Fixed pin definition in the symbol.")

        return item  # Return the item with fixed pin definition

    else:
        print("Undefined symbol definition, Pass.")
        
    return item

    

def find_symbol_in_lib(lib_sexp, symbol_name):
    """
    Find a symbol in a symbol library file.
    """
    for item in lib_sexp:
        if isinstance(item, list) and len(item) > 1 and item[0] == 'symbol' and item[1] == symbol_name:
            # If the symbol has an 'extends' section, we need to return the whole symbol based on the extend source
            if isinstance(item[2], list) and item[2][0] == 'extends':
                extends_source = item[2][1]
                ext_source_item = None
                for ext_item in lib_sexp:
                    if isinstance(ext_item, list) and len(ext_item) > 1 and ext_item[0] == 'symbol' and ext_item[1] == extends_source:
                        ext_source_item = ext_item
                if ext_source_item:
                    # Combine item and ext_source_item
                    combined_item = copy.deepcopy(ext_source_item)
                    origin_name = combined_item[1]  # Original name from the extends source
                    combined_item[1] = item[1]  # Update the name to the current symbol's name
                    # Also need to update the name of symbols in the combined item
                    for idx, val_item in enumerate(combined_item):
                        if isinstance(val_item, list) and len(val_item) > 1 and val_item[0] == 'symbol':
                            # Update the symbol name to the current symbol's name
                            combined_item[idx][1] = combined_item[idx][1].replace(origin_name.replace('"', ''), item[1].replace('"', ''))

                    # Update other properties from the original item
                    for val_item in item[3:]:
                        update_val_flag = False
                        # find the corresponding item in the extend source
                        for idx, ext_val_item in enumerate(combined_item[2:], start=2):
                            if isinstance(val_item, list) and isinstance(ext_val_item, list) and len(val_item) > 1 and len(ext_val_item) > 1: 
                                if val_item[0] == 'property'and ext_val_item[0] == 'property' and val_item[1] == ext_val_item[1]:
                                    # Find the same named property and update it
                                    combined_item[idx] = val_item
                                    update_val_flag = True
                        if not update_val_flag:
                            # If the property was not found in the extend source, append it
                            combined_item.append(val_item)
                    # Update the symbol info to the new one.
                    item = combined_item

                    item = fix_wrong_pin_def(item)  # Fix the pin definition if needed
                    return item

                else:
                    assert False, f"Symbol '{symbol_name}' extends from '{extends_source}' but it was not found in the library."
            else:
                item = fix_wrong_pin_def(item)  # Fix the pin definition if needed
                return item
    return None

def add_symbol_to_lib_symbols(sch_sexp, symbol_sexp):
    """
    Add a symbol to the lib_symbols section of a schematic.
    """
    lib_symbols_idx = find_lib_symbols_section(sch_sexp)
    if lib_symbols_idx is None:
        # Create lib_symbols section if it doesn't exist
        lib_symbols = ['lib_symbols']
        sch_sexp.append(lib_symbols)
        lib_symbols_idx = len(sch_sexp) - 1

    # if default symbol has pin_number hide, remove that.
    if len(symbol_sexp[3]) > 1 and symbol_sexp[3][0] == "pin_numbers" and symbol_sexp[3][1] == "hide":
        symbol_sexp.pop(3) # remove the pin_numbers hide
    
    sch_sexp[lib_symbols_idx].append(symbol_sexp)
    return sch_sexp

def generate_uuid():
    """
    Generate a UUID for KiCad.
    """
    return str(uuid.uuid4())

def get_symbol_ref_loc(symbol_lib):
    """
    Get the locations of the reference designator and value in the symbol library.
    Returns:
        tuple: (x1, y1, x2, y2) coordinates of the reference and value locations.
    """

    x1 = y1 = 0
    x2 = y2 = 0
    for item in symbol_lib:
        if isinstance(item, list) and len(item) > 1 and item[0] == 'property':
            if item[1] == '"Reference"':
                for sub_item in item:
                    if isinstance(sub_item, list) and sub_item[0] == 'at':
                        x1 = float(sub_item[1])
                        y1 = float(sub_item[2])
            elif item[1] == '"Value"':
                for sub_item in item:
                    if isinstance(sub_item, list) and sub_item[0] == 'at':
                        x2 = float(sub_item[1])
                        y2 = float(sub_item[2])
                break

            # if item[1] == '"Reference"':
            #     x1 = float(item[3][1])
            #     y1 = float(item[3][2])
            # elif item[1] == '"Value"':
            #     x2 = float(item[3][1])
            #     y2 = float(item[3][2])
            #     break

    return x1, y1, x2, y2


def get_default_footprint(lib_id):
    """
    Get the default footprint for a symbol.
    Args:
        lib_id (str): Library ID in the format "Device:R"
    Returns:
        str: Default footprint string
    """

    # TODO: Make the default footprint configurable through a config file

    footprint_dict = {
        "Device:R": "Resistor_SMD:R_0805_2012Metric",
        "Device:C": "Capacitor_SMD:C_0805_2012Metric",
        "Device:L": "Inductor_SMD:L_0805_2012Metric",
        "Device:LED": "LED_SMD:LED_0805_2012Metric",
    }

    # Assign the default footprint based on the library ID
    if lib_id in footprint_dict:
        footprint = footprint_dict[lib_id]
    else:
        # If no default footprint is found, return an empty string
        footprint = ""
    
    return footprint




def create_symbol_instance(lib_symbol, lib_id, x, y, rotation, reference, value, mirror, uuid_str=None):
    """
    Create a new symbol instance for placement in a schematic.
    
    Args:
        symbol (list): S-expression of the symbol to be instantiated
        lib_id (str): Library ID in the format "LibraryName:SymbolName"
        x, y (float): Position coordinates
        rotation (int): Rotation in degrees (0, 90, 180, 270)
        reference (str): Reference designator (e.g., "U2")
        value (str): Component value (e.g., "ESP32-WROOM-32")
        uuid_str (str, optional): UUID for the symbol. If None, generates a new one.
    
    Returns:
        list: S-expression for the symbol instance
    """
    if uuid_str is None:
        uuid_str = generate_uuid()

    ref_x, ref_y, val_x, val_y = get_symbol_ref_loc(lib_symbol)
    
    symbol = [
        'symbol',
        ['lib_id', lib_id],
        ['at', str(x), str(y), str(rotation)],
        ['unit', '1'],
        ['exclude_from_sim', 'no'],
        ['in_bom', 'yes'],
        ['on_board', 'yes'],
        ['dnp', 'no'],
        ['fields_autoplaced', 'yes'],
        ['uuid', uuid_str],
        ['property', '"Reference"', f'"{reference}"', 
            ['at', str(round(x+ref_x, 2)), str(round(y+ref_y,2)), str(rotation)],
            ['effects', 
                ['font', ['size', '1.27', '1.27']]
            ]
        ],
        ['property', 'Value', f'"{value}"',
            ['at', str(round(x+val_x,2)), str(round(y+val_y,2)), str(rotation)],
            ['effects', 
                ['font', ['size', '1.27', '1.27']]
            ]
        ]
    ]

    if mirror == "x":
        symbol.insert(3, ['mirror', 'x'])
    elif mirror == "y":
        symbol.insert(3, ['mirror', 'y'])

    # Whether the new symbol has a footprint property
    footprint_flag = False 

    # Append "Footprint", "Datasheet", and "Description" properties from the symbol library
    for prop in ['"Footprint"', '"Datasheet"', '"Description"']:
        for item in lib_symbol:
            if isinstance(item, list) and len(item) > 1 and item[0] == 'property' and item[1] == prop:
                if prop == '"Footprint"' and item[2] == "":
                    # If footprint is empty, replace it the default footprint
                    item[2] = get_default_footprint(lib_id)
                
                symbol.append(item)
                break

    return symbol

def add_symbol_instance_to_schematic(sch_sexp, symbol_instance):
    """
    Add a symbol instance to the schematic.
    """
    # Add the symbol after the last existing symbol
    for i in range(len(sch_sexp) - 1, -1, -1):
        item = sch_sexp[i]
        if isinstance(item, list) and item and item[0] == 'symbol':
            sch_sexp.insert(i + 1, symbol_instance)
            return sch_sexp
    
    # If no symbols found, add before sheet_instances
    for i in range(len(sch_sexp) - 1, -1, -1):
        item = sch_sexp[i]
        if isinstance(item, list) and item and item[0] == 'sheet_instances':
            sch_sexp.insert(i, symbol_instance)
            return sch_sexp
    
    # If no suitable position found, append to the end
    sch_sexp.append(symbol_instance)
    return sch_sexp


## Store bounding box information for symbols
#  Format: {symbol_name: (x1, y1, x2, y2)}
BOUNDING_BOX_DICT = {}

def clear_bounding_box_dict():
    """
    Clear the bounding box dictionary.
    This is useful for resetting the state before processing a new schematic.
    """
    global BOUNDING_BOX_DICT
    BOUNDING_BOX_DICT = {}
    # print("Cleared bounding box dictionary.")

def get_symbol_bounding_box(symbol_sexp, pos_x, pos_y, rotation=0, mirror=None):
    """
    Get the bounding box of a symbol in the schematic.
    
    Args:
        symbol_sexp (list): S-expression of the symbol
    
    Returns:
        tuple: (x1, y1, x2, y2) coordinates of the bounding box
    """
    x1 = x2 = pos_x
    y1 = y2 = pos_y
    # Initialize the bounding box coordinates

    # NOTE: the coordinates in the symbol definition are different from the schematic coordinates. Y axis is inverted.
    for item in symbol_sexp:
        # Find the symbol definition
        if isinstance(item, list) and len(item) > 2 and item[0] == 'symbol':
            # Get the bounding box coordinates from the symbol definition
            for sub_item in item[2:]:
                # 1. Get the boundary based on the pins.
                if isinstance(sub_item, list) and sub_item[0] == 'pin':
                    for val_item in sub_item:
                        if isinstance(val_item, list) and val_item[0] == 'at':
                            # Get the pin coordinates
                            pin_x = float(val_item[1]) + pos_x
                            pin_y = -float(val_item[2]) + pos_y # Y axis is inverted in KiCad for symbol versus schematic
                            x1 = min(x1, pin_x)
                            y1 = min(y1, pin_y)
                            x2 = max(x2, pin_x)
                            y2 = max(y2, pin_y)
                # 2. Get the boundary based on the symbol rectangle.
                elif isinstance(sub_item, list) and sub_item[0] == 'rectangle':
                    # Get the rectangle coordinates
                    for val_item in sub_item:
                        if isinstance(val_item, list) and val_item[0] == 'start':
                            # Get the rectangle start coordinates
                            rect_x1 = float(val_item[1]) + pos_x
                            rect_y1 = -float(val_item[2]) + pos_y
                            # Update the bounding box coordinates
                            x1 = min(x1, rect_x1)
                            y1 = min(y1, rect_y1)
                            # x2 = max(x2, rect_x1)
                            # y2 = max(y2, rect_y1)
                        elif isinstance(val_item, list) and val_item[0] == 'end':
                            # Get the rectangle end coordinates
                            rect_x2 = float(val_item[1]) + pos_x
                            rect_y2 = -float(val_item[2]) + pos_y
                            # Update the bounding box coordinates
                            # x1 = min(x1, rect_x2)
                            # y1 = min(y1, rect_y2)
                            x2 = max(x2, rect_x2)
                            y2 = max(y2, rect_y2)

    # If one dimension of the bounding box is zero, that means the symbol uses various unexpected shapes.
    # For example, a capacitor symbol with two pins along a line
    dxdy_size_dict = {
        "Device:C": (2, 0, 2, 0),  # Extra width for capacitor symbols
        "power:+": (1, 2.5, 1, 0),  # Extra width for power symbols
        "power:GND": (1, 0, 1, 2.5),  # Extra width for power symbols
    }

    # If the bounding box is too small, we need to adjust it based on the symbol type
    if abs(x1-x2) < 0.01 or abs(y1-y2) < 0.01:
        dx1, dy1, dx2, dy2 = (0, 0, 0, 0)  # Default values if no match found
        for key, value in dxdy_size_dict.items():
            if key in symbol_sexp[1]:
                dx1, dy1, dx2, dy2 = value
                break
        
        # Adjust the bounding box size
        x1 -= dx1
        y1 -= dy1
        x2 += dx2
        y2 += dy2

    
    # Adjust the bounding box based on the rotation, counter-clockwise
    if rotation != 0:
        assert rotation in [0, 90, 180, 270], "Rotation must be one of [0, 90, 180, 270] degrees."
        # For 90 degrees rotation, swap x and y coordinates
        if rotation == 90 or rotation == 270:
            dx, dy = x2 - x1, y2 - y1
            x1, y1 = pos_x - dy / 2, pos_y - dx / 2
            x2, y2 = pos_x + dy / 2, pos_y + dx / 2

    if mirror == "x":
        # Mirror along the x-axis, swap y coordinates
        y1, y2 = pos_y - (y2 - pos_y), pos_y - (y1 - pos_y)
    elif mirror == "y":
        # Mirror along the y-axis, swap x coordinates
        x1, x2 = pos_x - (x2 - pos_x), pos_x - (x1 - pos_x)

    return (x1, y1, x2, y2)


def check_box_overlap(symbol_box):
    """
    Check if the bounding box of a symbol overlaps with existing symbols.
    
    Args:
        symbol_box (tuple): (x1, y1, x2, y2) coordinates of the bounding box
    
    Returns:
        dict: the entry that overlaps with the symbol box, or None if no overlap
    """
    fp_tolerance = 0  # Tolerance for floating point comparison

    overlap_threshold = 1.27 # max overlap distance allowed for the sum of the overlap distance in x and y direction

    overlapped_symbols = {}

    x1, y1, x2, y2 = symbol_box
    for sym_name, box in BOUNDING_BOX_DICT.items():
        bx1, by1, bx2, by2 = box
        # Check for any overlap
        if not (x2 < bx1+fp_tolerance or x1 > bx2-fp_tolerance or y2 < by1+fp_tolerance or y1 > by2-fp_tolerance):
            
            # Calculate overlap in x and y directions
            overlap_x = min(x2, bx2) - max(x1, bx1)
            overlap_y = min(y2, by2) - max(y1, by1)
            # Only consider positive overlaps
            overlap_x = max(0, overlap_x)
            overlap_y = max(0, overlap_y)
            overlap_sum = overlap_x + overlap_y
            if overlap_sum > overlap_threshold:
                # print(f"Existing '{sym_name}' overlaps with new bounding box {box_to_str(symbol_box)}")
                overlapped_symbols[sym_name] = box
    
    if overlapped_symbols:
        return overlapped_symbols
    else:
        return None

def check_position_overlap(x, y):
    """
    Check if the position (x, y) overlaps with existing symbols.
    
    Args:
        x (float): X coordinate of the position
        y (float): Y coordinate of the position
    
    Returns:
        dict: the entry that overlaps with the position, or None if no overlap
    """
    overlapped_symbols = {}
    # Prepare the bounding box for the position
    for sym_name, box in BOUNDING_BOX_DICT.items():
        bx1, by1, bx2, by2 = box
        # Check if the position is within the bounding box
        if bx1 < x < bx2 and by1 < y < by2:
            print(f"Position ({x}, {y}) overlaps with symbol '{sym_name}' at bounding box {box}")
            overlapped_symbols[sym_name] = box
    
    if overlapped_symbols:
        return overlapped_symbols
    else:
        return None
    

def box_to_str(box) -> str:
    """
    Convert a bounding box tuple to a string representation.
    
    Args:
        box (tuple): (x1, y1, x2, y2) coordinates of the bounding box
    
    Returns:
        str: String representation of the bounding box
    """
    return f"upper_left_corner ({box[0]:.3f}, {reY(box[1]):.3f}), bottom_right_corner ({box[2]:.3f}, {reY(box[3]):.3f})"

    
def check_position_overlap_error(type, reference, x, y):
    """
    Check whether the current new label position will overlap with existing symbols, labels or wires.
    If there is an overlap, then raise an error.
    """
    overlap_symbols = check_position_overlap(x, y)
    
    if overlap_symbols:
        # If there is an overlap, raise an error
        overlap_info = '\n'.join([f"{name}: {box_to_str(box)}" for name, box in overlap_symbols.items()])
        if RAISE_ERR_FLAG:
            raise ValueError(f"{type} with reference {reference} (position x: {x}, y: {reY(y)}) overlaps with existing symbols: \n [{overlap_info}]")
        else:
            print(f"Error: {type} with reference {reference} (position x: {x}, y: {reY(y)}) overlaps with existing symbols: \n [{overlap_info}]")
    
    # If do not raise error, create a temporary name for the bounding box and store it
    tmp_name = type + " - " + reference
    # Store the bounding box in the dictionary
    BOUNDING_BOX_DICT[tmp_name] = (x, y, x, y)

    

def check_box_overlap_error(bounding_box, symbol_name, reference, x, y, auto_route_try: bool = False):
    overlap_symbols = check_box_overlap(bounding_box)
    if overlap_symbols:
        # First test whether the symbol is a wire, if so, we can remove the overlap wires that end/start at the same position (they are in the same net!).
        if "wire" in symbol_name.lower():
            for op_name, box in overlap_symbols.copy().items():
                if "wire" in op_name.lower():
                    # print(f"Warning: wire of {box_to_str(bounding_box)} overlaps with {op_name} at {box_to_str(box)}")

                    # Check if the wire bounding box overlaps at either end of the box.
                    if (abs(box[0] - bounding_box[0]) < 0.01 and abs(box[1] - bounding_box[1]) < 0.01) or \
                        (abs(box[2] - bounding_box[2]) < 0.01 and abs(box[3] - bounding_box[3]) < 0.01) or \
                        (abs(box[0] - bounding_box[2]) < 0.01 and abs(box[1] - bounding_box[3]) < 0.01) or \
                        (abs(box[2] - bounding_box[0]) < 0.01 and abs(box[3] - bounding_box[1]) < 0.01):
                            # If the overlap is with a wire that shares one end, we can remove it from the overlap symbols
                            overlap_symbols.pop(op_name)
        # If still there is an overlap, raise an error
        if overlap_symbols:
            overlap_info = '\n'.join([f"{name}: {box_to_str(box)}" for name, box in overlap_symbols.items()])
            if RAISE_ERR_FLAG:
                raise ValueError(f"Symbol '{symbol_name}' with reference {reference} (center x: {x:.3f}, y: {reY(y):.3f}), with bounding box: {box_to_str(bounding_box)}\n overlaps with existing symbols: \n [ {overlap_info} ]")
            else:
                if not auto_route_try: # suppress the error for auto-routing
                    print(f"Error: Symbol '{symbol_name}' with reference {reference} (center x: {x:.3f}, y: {reY(y):.3f}), with bounding box: {box_to_str(bounding_box)}\n overlaps with existing symbols: \n [ {overlap_info} ]")

    ## To keep the code going, we will not raise an error here, only return the overlap symbols for upper caller to handle.
    # Create a name for the bounding box and store it
    tmp_name = symbol_name + " - " + reference
    # Store the bounding box in the dictionary
    BOUNDING_BOX_DICT[tmp_name] = bounding_box

    if overlap_symbols and len(overlap_symbols) > 0:
        return overlap_symbols 
    else:
        return None


def add_symbol_from_lib(sch_filename, sym_filename, symbol_name, lib_name, x, y, rotation, reference, value, mirror=None,output_filename=None):
    """
    Add a symbol from a symbol library to a schematic.
    
    Args:
        sch_filename (str): Path to input schematic file
        sym_filename (str): Path to symbol library file
        symbol_name (str): Name of the symbol in the library
        lib_name (str): Name of the library (used in lib_id)
        x, y (float): Position coordinates
        rotation (int): Rotation in degrees
        reference (str): Reference designator
        value (str): Component value
        output_filename (str): Path to output schematic file. If None, overwrites input file.
    """
    # Read the files
    sch_sexp = read_kicad_sch(sch_filename)
    sym_sexp = read_kicad_sym(sym_filename)

    # prepare the x, y coordinates, must be units of 1.27 mm due to 50 mil grid
    x = round(x / 1.27) * 1.27
    y = round(y / 1.27) * 1.27
    
    # Find the symbol in the library
    symbol = find_symbol_in_lib(sym_sexp, symbol_name)
    if not symbol:
        # Add qutoes to the symbol name for compatibility
        symbol = find_symbol_in_lib(sym_sexp, f'"{symbol_name}"')
    if not symbol:
        raise ValueError(f"Symbol '{symbol_name}' not found in library")

    
    lib_id = f'"{lib_name}:{symbol_name}"'

    # Add the symbol to lib_symbols section
    symbol[1] = lib_id
    sch_sexp = add_symbol_to_lib_symbols(sch_sexp, copy.deepcopy(symbol))
    
    # Create a new symbol instance
    symbol_instance = create_symbol_instance(symbol, lib_id, x, y, rotation, reference, value, mirror)
    
    # Add pin UUIDs
    pins = extract_pins_from_symbol(symbol)
    # symbol_instance = symbol_instance.append(pins)
    for pin in pins:
        symbol_instance.append(pin)

    # Add empty instances section to complete the structure
    sch_filename_base = sch_filename.split('/')[-1].split('.')[0] # Get the base name of the schematic file
    uuid_str = sch_sexp[4][1] if sch_sexp[4] and sch_sexp[4][0] == "uuid" else "None UUID?"
    uuid_str = uuid_str[1:-1] if uuid_str.startswith('"') and uuid_str.endswith('"') else uuid_str
    symbol_instance.append(['instances', ['project', f'"{sch_filename_base}"', ['path', f'"/{uuid_str}"', ['reference', f'"{reference}"'], ['unit', '1']]]])
    
    
    # Add the symbol instance to the schematic
    sch_sexp = add_symbol_instance_to_schematic(sch_sexp, symbol_instance)
    
    # Write the output file
    output_file = output_filename or sch_filename
    write_kicad_sch(sch_sexp, output_file)


    ## NOTE: Put the error check after file writing by design, so that we can get the incorrect schematic image for LLM feedback.
    # Get the bounding box of the symbol
    bounding_box = get_symbol_bounding_box(symbol, x, y, rotation, mirror)
    # # Check for overlaps, if no overlap, store the bounding box
    check_box_overlap_error(bounding_box, symbol_name, reference, x, y)
    
    return symbol_instance

def extract_pins_from_symbol(symbol_sexp):
    """
    Extract pin definitions from a symbol.
    Returns a list of pin S-expressions.
    """
    pins = []
    # Look for the _1_1 part which contains pins
    for item in symbol_sexp:
        if isinstance(item, list) and len(item) > 2 and item[0] == 'symbol' and item[2][0] == 'pin':
            for pin_info in item[2:]:
                if isinstance(pin_info, list) and len(pin_info) > 1 and pin_info[0] == 'pin':
                    for p_item in pin_info:
                        if isinstance(p_item, list) and len(p_item) > 1 and p_item[0] == 'number':
                            # Extract the pin number
                            pin_number = p_item[1]
                            break                    # (pin "38"
                    #     (uuid "6596f83f-54a4-491e-a0d5-209410e34a52")
                    # )
                    pins.append(['pin', pin_number, ['uuid', generate_uuid()]])


    # Append "Pin" properties from the symbol library
    # for item in lib_symbol:
    #     if isinstance(item, list) and len(item) > 2 and item[0] == 'symbol' and item[2][0] == 'pin':
            # for pin_info in item[2:]:
            #     if isinstance(pin_info, list) and len(pin_info) > 1 and pin_info[0] == 'pin':
            #         for p_item in pin_info:
            #             if isinstance(p_item, list) and len(p_item) > 1 and p_item[0] == 'number':
            #                 # Extract the pin number
            #                 pin_number = p_item[1]
            #                 break                    # (pin "38"
            #         #     (uuid "6596f83f-54a4-491e-a0d5-209410e34a52")
            #         # )
            #         pins.append(['pin', pin_number, ['uuid', generate_uuid()]])


    return pins


# Example usage
if __name__ == "__main__":

    # Example: Add a symbol to a schematic
    add_symbol_from_lib(
        sch_filename="./create_symbols/create_symbols.kicad_sch",
        sym_filename=KICAD_SYMBOL_LIB_PATH + "\\RF_Module.kicad_sym",
        symbol_name="ESP-WROOM-02",
        lib_name="RF_Module",
        x=150.0,
        y=100.0,
        rotation=0,
        reference="U2",
        value="ESP-WROOM-02",
        output_filename=None
    )