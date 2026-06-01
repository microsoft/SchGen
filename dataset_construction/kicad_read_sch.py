import os, sys
from pathlib import Path
proj_path = Path(os.environ["PROJECT_PATH"])
sys.path.append(str(proj_path))

import my_skip_lib
import argparse
from collections import defaultdict, deque
import re
from pathlib import Path

from modules.kicad_sch_interface import reY, RAISE_ERR_FLAG, REVERSE_Y_FLAG, is_label_ref, change_unit_to_grid

"""
L1: Relative position + pin connection
L2: Absolute position + pin connection
L3: Absolute position + direct wire 
"""

code_representation_level = "L1"


def sanitize_symbol_name(name: str) -> str:
    """
    Convert symbol name to a valid Python identifier.
    """
    name = name.lstrip('#')                 # Remove leading '#' (e.g. '#PWR0123' -> 'PWR0123')
    name = re.sub(r'\W+', '_', name)        # Replace non-word characters with '_'
    if re.match(r'^\d', name):
        name = 'S_' + name
    return name

class code_generator:

    def __init__(self, module_name, sch_ref_path, output_path):

        self.module_name = module_name
        self.schematic = my_skip_lib.Schematic(sch_ref_path)
        self.output_path = output_path
        self.pin_location_map = dict()     # (x, y) → (ref, pin_number)
        self.pin_location_name_map = dict() # (x, 7) -> (ref, pin_name) semantic meaningful pin names.
        self.wire_location_map = dict() # (x, y) → wire
        self.existed_pairs = set() # Store the pairs of coordinates that have been connected
        self.wire_segment = None # Store the wire segments that have been merged
        self.net_set = {} # Used for disjoint set operations

        self.label_location_map = dict()   # (x, y) → label_text
        self.label_ref_map = {}  #  label_ref -> label_pos,  Maps label reference to its positions


        self.global_conn_graph = defaultdict(set) # Used to build the connection graph from wires

        # Build the mapping from coordinates to pin locations, label locations, and wire segments
        self.build_mapping()


    def get_pin_name(self, pin_coord):
        # try the semantic name as well
        pin_info_name = self.pin_location_name_map.get(pin_coord, None)

        # if pin name is available and not one of those special names, we can use names to identify pins instead of some random number!
        if pin_info_name and pin_info_name[1] not in ["nan", "NC", "GND", "~"]:
            _, pin_name = pin_info_name
        else:
            pin_name = None

        return pin_name


    def symbol_to_script(self, component, cnt):
        '''
        Read the symbol and generate code line to place the symbol in the schematic
        component: my_skip_lib.eeschema.schematic.symbol.Symbol
        cnt: int, the index of the center symbol in the cluster
        '''    
        lib_id = component.lib_id.value  # e.g. "Device:R" or "power:+3.3V"
        if ":" in lib_id:
            symbol_lib, symbol_name = lib_id.split(":", 1)
        else:
            symbol_lib = lib_id
            symbol_name = ""

        pos = component.at.value if hasattr(component.at, "value") else component.at  # [x, y, rot]
        pos_x, pos_y = pos[0], pos[1]
        rotation = pos[2] if len(pos) > 2 else 0

        reference = component.Reference.value if hasattr(component, "Reference") else ""
        value = component.Value.value if hasattr(component, "Value") else ""
        mirror = None
        if hasattr(component.mirror, 'value'):
            # If already has mirror attribute, update its value
            mirror = component.mirror.value

        code_line = None
        if pos_x == self.center_x and pos_y == self.center_y:
            # If the symbol is the center of a cluster, we specify its coordinates with center_x and center_y
            code_line = (
                f'add_schematic_symbol('
                f'symbol_lib="{symbol_lib}", '
                f'symbol_name="{symbol_name}", '
                f'pos_x=center_x_{cnt}, pos_y=center_y_{cnt}, '
                f'reference="{reference}", '
                f'value="{value}", '
                f'rotation={rotation}, '
                f'mirror="{mirror}")'
            )
        else:
            # If the symbol is not the center of a cluster, we specify its coordinates with respect to the center symbol
            x_off = round(pos_x - self.center_x, 2)
            y_off = round(pos_y - self.center_y, 2)
            if REVERSE_Y_FLAG:
                y_off = -y_off

            # Grid representation
            # x_off = change_unit_to_grid(x_off)
            # y_off = change_unit_to_grid(y_off)
            # x_off = change_unit_to_grid(x_off)
            # y_off = change_unit_to_grid(y_off)

            # Integer representation
            # Float representation
            x_off = int(x_off)
            y_off = int(y_off)
            x_off = int(x_off)
            y_off = int(y_off)
            if code_representation_level != "L1": # L2 and L3 both use absolute position
                code_line = (
                    f'add_schematic_symbol('
                    f'symbol_lib="{symbol_lib}", '
                    f'symbol_name="{symbol_name}", '
                    f'pos_x={pos_x}, pos_y={pos_y}, '
                    f'reference="{reference}", '
                    f'value="{value}", '
                    f'rotation={rotation}, '
                    f'mirror="{mirror}")'
                )
            else:
                code_line = (
                    f'add_schematic_symbol('
                    f'symbol_lib="{symbol_lib}", '
                    f'symbol_name="{symbol_name}", '
                    f'pos_x=center_x_{cnt} + ({x_off}), pos_y=center_y_{cnt} + ({y_off}), '
                    f'reference="{reference}", '
                    f'value="{value}", '
                    f'rotation={rotation}, '
                    f'mirror="{mirror}")'
                )
        return code_line

    def line_to_script(self, line):

        '''
        Read the wire line and generate code line to place the wire in the schematic
        line: my_skip_lib.eeschema.schematic.wire.Wire
        '''
        start = line.start.value if hasattr(line.start, "value") else line.start
        end = line.end.value if hasattr(line.end, "value") else line.end
        start_x, start_y = start[0], start[1]
        end_x, end_y = end[0], end[1]

        if REVERSE_Y_FLAG:
            start_y = reY(start_y)
            end_y = reY(end_y)

        return f'add_new_wire([{start_x}, {start_y}], [{end_x}, {end_y}])'

    def place_label(self, label):
        '''
        Read the label and generate code line to place the label in the schematic
        label: my_skip_lib.eeschema.schematic.label.GlobalLabel
        '''

        # 1. label_text
        label_text = label.value

        # 2. label_type
        label_type = label.shape.value if hasattr(label, "shape") else "input"

        # 3. label_pos (x, y)
        at = label.at.value if hasattr(label.at, "value") else label.at
        label_pos = [float(at[0]), float(at[1]), float(at[2])] if len(at) > 2 else [float(at[0]), float(at[1]), 0.0]

        lines= []

        # if DEBUG:
        #     print(label_text, label_pos)
        # label orientation based rotation angle
        if abs(label_pos[2] - 0.0) < 1e-6:
            label_orient = "right"
        elif abs(label_pos[2] - 90.0) < 1e-6:
            label_orient = "up"
        elif abs(label_pos[2] - 180.0) < 1e-6:
            label_orient = "left"
        elif abs(label_pos[2] - 270.0) < 1e-6:
            label_orient = "down"


        # Generate a unique reference for the label
        label_text, label_id = self.label_location_map[tuple(label_pos[:2])]

        # # Place the label in the schematic
        # lines.append(
        #     f'add_label('
        #     f'label_pos={label_pos[:2]}, '
        #     f'label_text="{label_text}", '
        #     f'label_ref="{label_text}_{label_id}", '
        #     f'label_type="{label_type}", '
        #     f'text_orient="{label_orient}")'
        # )

        # Find all the pins that are connected to this label (direct or indirect connections)
        connected = self.find_connected_endpoints(tuple(label_pos[:2]))

        if REVERSE_Y_FLAG:
            label_pos[1] = reY(label_pos[1])
            
        if not connected:
            print(f"[Warning] No connected pins found for label '{label_text}' at {label_pos[:2]}.")
            return

        # sort by distance
        connected = sorted(connected, key=lambda x: (x[2], x[1]))

        # get the closest connected point
        conn_coord, _, _ = connected[0] if connected else (None, None, None)

        
        pin_info = self.all_points_map[conn_coord]
        
        pin_name = self.get_pin_name(conn_coord)


        # Calulate relative position offset for the label
        start = label_pos[:2]
        end = conn_coord
        if REVERSE_Y_FLAG:
            ey = reY(end[1])
        offset_x = round(start[0] - end[0], 2)
        offset_y = round(start[1] - ey, 2)

        # Grid representation
        # offset_x = change_unit_to_grid(offset_x)
        # offset_y = change_unit_to_grid(offset_y)
        # offset_x = change_unit_to_grid(offset_x)
        # offset_y = change_unit_to_grid(offset_y)

        # Float representation
        offset_x = int(offset_x)
        offset_y = int(offset_y)
        offset_x = int(offset_x)
        offset_y = int(offset_y)

        # Integer representation

        # if REVERSE_Y_FLAG:
        #     offset_y = -offset_y

        symbol, pin_id_str = pin_info
        sym_var = sanitize_symbol_name(symbol)
        varstub = f"{sym_var}_{pin_id_str}"

        pin_name = pin_name if pin_name is not None else pin_id_str
        if code_representation_level != "L1": # L1 and L2 directly add labels with absolute position
            lines.append(f"# Add label {label_text}")
            if code_representation_level == "L2": # L2 connect label to pin with absolute position
                lines.append(
                    f'add_label('
                    f'label_pos=[{label_pos[0]}, {label_pos[1]}], '
                    f'label_text="{label_text}", '
                    f'label_ref="{label_text}_{label_id}", '
                    f'label_type="{label_type}", '
                    f'text_orient="{label_orient}"'
                    f')'
                )
                lines.append(f"# Connecting Label {label_text} label_id:{label_id} to {symbol} pin {pin_name} (Pin ID {pin_id_str} -- Name {pin_name})")
                lines.append(f'connect_pins("{label_text}_{label_id}", "1", "{symbol}", "{pin_name}")\n')
            else: # L3 directly add label with absolute position without connection
                lines.append(
                    f'add_label('
                    f'label_pos=[{label_pos[0]}, {label_pos[1]}], '
                    f'label_text="{label_text}", '
                    f'label_ref="{label_text}_{label_id}", '
                    f'label_type="{label_type}", '
                    f'text_orient="{label_orient}"'
                    f')'
                )
        else: # L1 add label with relative position and connect to pin
            lines.append(f"# Add label {label_text} next to {symbol} pin {pin_name} ")
            lines.append(
                f'x_{varstub}, y_{varstub} = get_pin_location('
                f'symbol_ref="{symbol}", '
                f'pin_name="{pin_name}")'
            )

            lines.append(
                f'add_label('
                f'label_pos=[x_{varstub}+({offset_x}), y_{varstub}+({offset_y})], '
                f'label_text="{label_text}", '
                f'label_ref="{label_text}_{label_id}", '
                f'label_type="{label_type}", '
                f'text_orient="{label_orient}"'
                f')'
            )
            if code_representation_level != "L3":
                lines.append(f"# Connecting Label {label_text} label_id:{label_id} to {symbol} pin {pin_name} (Pin ID {pin_id_str} -- Name {pin_name})")
                lines.append(f'connect_pins("{label_text}_{label_id}", "1", "{symbol}", "{pin_name}")\n')

        return "\n".join(lines)


    # From a given start point, find all pins and labels that are connected to it, and return a list of tuples 
    def find_connected_endpoints(self, start):
        '''
        From a given start point, find all pins and labels that are connected to it, and return a list of tuples 
        [(connected_point, wire_seg_num, physical distance), ...]
        
        Arg:
        start: tuple, the starting point (x, y)

        '''
        visited = set()
        queue = deque([(start, 0, 0)])  # (node, wire_seg_num, distance)
        connected = []

        while queue:
            node, wire_seg_num, dist = queue.popleft()
            if node in visited:
                continue
            visited.add(node)


            if node != start and node in self.all_points_map:
                if tuple([start, node]) not in self.existed_pairs:
                    # if the connection is new, add it to the existed_pairs and connected list
                    # NOTE: only new connection will be appened and returned by this function.
                    self.existed_pairs.add(tuple([start, node]))
                    self.existed_pairs.add(tuple([node, start]))
                    connected.append((node, wire_seg_num, dist))

            # Loop over all neighbors in the global connection graph
            for neighbor in self.global_conn_graph[node]:
                assert neighbor[0] == node[0] or neighbor[1] == node[1], "Neighbor coordinates do not match with start point coordinates."
                delta_dist = abs(neighbor[0] - node[0]) + abs(neighbor[1] - node[1])
                if neighbor not in visited:
                    queue.append((neighbor, wire_seg_num + 1, dist + delta_dist))

        return connected

    # Below are find and union functions for disjoint set operations
    def find(self, x):
        '''
        Find the root of x in the disjoint set, and compress the path.
        x: the element to find the root of
        '''
        # Ensure x is in the parent dictionary; if not, set its parent to itself
        self.net_set.setdefault(x, x)
        # If x is not its own parent, recursively find the root and compress the path
        if self.net_set[x] != x:
            self.net_set[x] = self.find(self.net_set[x])
        # Return the root of x
        return self.net_set[x]

    def union(self, x, y):
        '''
        Union the sets containing x and y, if they are not already in the same set.
        x: the first element
        y: the second element
        '''
        # Find the roots of x and y
        rx, ry = self.find(x), self.find(y)
        # If roots are different, merge the sets by making one root point to the other
        if rx != ry:
            self.net_set[ry] = rx
            return True  # Sets were merged
        return False  # x and y were already in the same set
    
    # Process the junctions in the schematic by finding all connected pin pairs
    def connect_wires(self, symbol_set):
        '''
        Process the junctions in the schematic by finding all connected pin pairs.
        symbol_set: set of symbols in the schematic
        '''
        
        lines = []        
        candidate_connections = []

        # Iterate through all pins in the symbol set to find connected pins
        for component in symbol_set:
            # first find all pins
            pins = []
            if isinstance(component.pin, my_skip_lib.sexp.parser.ParsedValue):
                pins = [tuple(component.pin.parent.at.value[:2])]
            else:
                pins = [tuple(pin.location.value[:2]) for pin in component.pin
                        if isinstance(pin, my_skip_lib.eeschema.schematic.symbol.SymbolPin)]
            # For each pin, find all connected endpoints and append to candidate_connections
            for pin_pos in pins:
                for c, wire_seg_num, dist in self.find_connected_endpoints(pin_pos):
                    obj1 = self.all_points_map[pin_pos]
                    obj2 = self.all_points_map[c]
                    key = tuple(sorted([(pin_pos, obj1), (c, obj2)]))
                    # append the candidate connection
                    candidate_connections.append((dist, wire_seg_num, key))

        # Sort the candidate connections by distance, and then by edge count, candidate connections should include all the indirectly-connected pin pairs
        candidate_connections.sort(key=lambda x: (x[0], x[1]))

        for dist, wire_seg_num, ((coord1, obj1), (coord2, obj2)) in candidate_connections:

            # If the coordinates are not belong to the same set, we can connect them
            if self.union(coord1, coord2):
                ref_start, pin_number_start = obj1
                ref_end, pin_number_end = obj2

                pin_name_start, pin_name_end = self.get_pin_name(coord1), self.get_pin_name(coord2)
                # If a semantic meaningful pin name is available, we use it. otherwise, use the pin ID number
                final_pin_name_start = pin_name_start if pin_name_start is not None else pin_number_start
                final_pin_name_end = pin_name_end if pin_name_end is not None else pin_number_end

                lines.append(f"\n# Connecting {ref_start} pin {final_pin_name_start} (Pin ID {pin_number_start} -- Name {pin_name_start}) to {ref_end} pin {final_pin_name_end} (Pin ID {pin_number_end} -- Name {pin_name_end})")
                if is_label_ref(ref_start, final_pin_name_start) and is_label_ref(ref_end, final_pin_name_end):
                    raise ValueError(f"Should not handle labels here, need update code.")
                lines.append(f'connect_pins("{ref_start}", "{final_pin_name_start}", "{ref_end}", "{final_pin_name_end}")')

        return lines

    # Get all connected subgraphs in the schematic
    def get_connected_subgraphs(self):
        '''
        This function finds all connected subgraphs in the schematic.
        '''
        coord_to_symbol = defaultdict(set) # Maps coordinates to symbols
        coord_to_label = defaultdict(set) # Maps coordinates to labels
        symbol_pin_coords = defaultdict(set) # Maps symbols to their pin coordinates

        # Get the location map from symbols, labels and wires to locations
        for component in self.schematic.symbol:

            # If the component belongs to single pin symbol
            if isinstance(component.pin, my_skip_lib.sexp.parser.ParsedValue):
                coord = tuple(component.pin.parent.at.value[:2])
                coord_to_symbol[coord].add(component)
                symbol_pin_coords[component].add(coord)
            # If the component has multiple pins
            else:
                for pin in component.pin: 
                    if isinstance(pin, my_skip_lib.eeschema.schematic.symbol.SymbolPin):
                        coord = tuple(pin.location.value[:2])
                        coord_to_symbol[coord].add(component)
                        symbol_pin_coords[component].add(coord)

        # Get the location map from labels to locations
        for label in self.schematic.global_label:
            at = label.at.value if hasattr(label.at, "value") else label.at
            coord = tuple(at[:2])
            coord_to_label[coord].add(label)
        
        # Get graph that represents the connections between coordinates
        graph = defaultdict(set)
        # First, copy the existing graph from the schematic, which contains connections between symbols/labels
        for k, v in self.global_conn_graph.items():
            graph[k] = set(v)
        # Second, for all the pins on the same symbol, connect them to each other
        for coords in symbol_pin_coords.values():
            coord_list = list(coords)
            for i in range(len(coord_list)):
                for j in range(i + 1, len(coord_list)):
                    a, b = coord_list[i], coord_list[j]
                    graph[a].add(b)
                    graph[b].add(a)
        # Record all the coordinates that have symbols or labels
        all_coords = set(graph.keys()) | set(coord_to_symbol.keys()) | set(coord_to_label.keys())
        for coord in all_coords:
            graph.setdefault(coord, set())

        # Finally, we do a BFS to find all connected subgraphs in the graph
        # Record three sets: symbols, labels, and wires in each component
        visited = set()
        subgraphs = []

        for coord in all_coords:
            if coord in visited:
                continue

            queue = deque([coord])
            visited.add(coord)
            symbol_set = set()
            label_set = set()
            wire_set = set()

            while queue:
                curr = queue.popleft()

                # If the current coordinate has a symbol, add it to the symbol set
                for sym in coord_to_symbol.get(curr, []):
                    symbol_set.add(sym)

                # If the current coordinate has a label, add it to the label set
                for label in coord_to_label.get(curr, []):
                    label_set.add(label)

                # If the current coordinate has a wire between itself and its neighbor, add it to the wire set
                for neighbor in graph[curr]:
                    if tuple([tuple(curr), tuple(neighbor)]) in self.wire_location_map:
                        wire_set.add(self.wire_location_map[tuple([tuple(curr), tuple(neighbor)])])
                        

                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            # If we have found at least one symbol in this component, we can determine the center symbol from it.
            if symbol_set:
                center_symbol = max(
                    symbol_set,
                    key=lambda s: len(s.pin) if not isinstance(s.pin, my_skip_lib.sexp.parser.ParsedValue) else 1
                )
                subgraphs.append((center_symbol, symbol_set, label_set, wire_set))

        return subgraphs

    def work(self):
        '''
        Main work function to process the schematic.
        '''

        def get_symbol_relative_offsets(center_symbol, symbol_set):
            """
            Get the relative offsets of all symbols in the symbol_set with respect to the center_symbol.
            """
            symbol_with_offsets = []
            for component in symbol_set:
                if component == center_symbol:
                    continue
                pos = component.at.value if hasattr(component.at, "value") else component.at
                x_off = round(pos[0] - self.center_x, 3)
                y_off = round(pos[1] - self.center_y, 3)
                if REVERSE_Y_FLAG:
                    y_off = -y_off
                symbol_with_offsets.append((component, x_off, y_off))
            return symbol_with_offsets
    

        lines = []

        # Step 1: Initialize the script with necessary imports and set the schematic filename
        lines.append("import sys")
        lines.append("import os\n")

        lines.append("# Get project path and import kicad schematic interface")
        lines.append(f"PROJECT_PATH = os.environ['PROJECT_PATH']")
        lines.append(f"sys.path.append(PROJECT_PATH)")
        lines.append("from modules.kicad_sch_interface import *")

        # Step 2: Get all connected subgraphs in the schematic
        subgraphs = self.get_connected_subgraphs()
        print(f"Found {len(subgraphs)} connected subgraphs in the schematic.")

        # Step 3: For each subgraph, we will place the center symbol and other symbols, labels, and wires
        cnt = 1
        for center_symbol, symbol_set, label_set, wire_set in subgraphs:

            self.wires_with_junctions = []
            self.center_x, self.center_y = center_symbol.at.value[:2]
            if REVERSE_Y_FLAG:
                re_center_y = reY(self.center_y)
            
            # Step 3.1: Place the center symbol
            lines.append(f"\n### Placing center symbol {cnt} : {center_symbol.lib_id.value}###\n")
            if code_representation_level == "L1": # For L1, we place the center symbol at a fixed position (150, 110) to make sure all the relative offsets are positive and easier to read and understand. For L2 and L3, we place the center symbol at its original position.
                lines.append("center_x_{}, center_y_{} = 150.0, 110.0\n".format(cnt, cnt))
            else:
                lines.append(f"center_x_{cnt}, center_y_{cnt} = {self.center_x}, {re_center_y}\n")
            lines.append(self.symbol_to_script(center_symbol, cnt))
            
            # Step 3.2: Place other symbols with respect to the center symbol
            lines.append(f"\n### Placing other symbols in the Schematic with respect to the center symbol {cnt}###\n")

            # Step 3.2.1: Get the relative offsets of all symbols in the symbol_set with respect to the center_symbol
            symbol_with_offsets = get_symbol_relative_offsets(center_symbol, symbol_set)

            # Sort the symbols by their offsets, first by x_off, then by y_off
            symbol_with_offsets.sort(key=lambda item: (item[1], -item[2]))

            # Step 3.2.2: Call symbol_to_script for each component
            for component, _, _ in symbol_with_offsets:
                line = self.symbol_to_script(component, cnt)
                lines.append(line)


            # Step 3.3: Place global labels and connect them to pins
            lines.append("\n### Placing all global labels in the Schematic and connect them to the neighbor pin ###\n")
            # sort labels by their positions, first by x, then by y
            for label in label_set:
                at = label.at.value if hasattr(label.at, "value") else label.at
                label_pos = [float(at[0]), float(at[1]), float(at[2])] if len(at) > 2 else [float(at[0]), float(at[1]), 0.0]
                label._sort_key = (label_pos[0], -label_pos[1])  # Sort by x ascending, then by y descending
            label_set = sorted(label_set, key=lambda l: l._sort_key)
            
            for label in label_set:
                # line = self.label_to_script(label)
                line = self.place_label(label)
                lines.append(line)

            if code_representation_level != "L3":
                # Step 3.4: Connect all wires in the schematic
                lines.append("\n### Connecting all wires in the Schematic ###\n")
                lines.extend(self.connect_wires(symbol_set))
            else:
                lines.append("\n### Adding all wires in the Schematic ###\n")
                lines.extend([self.line_to_script(wire) for wire in wire_set])

            cnt += 1

        # Step 4: Write out all wires
        lines.append("\nwrite_out_all_wires()")

        # Save to output file
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write("# Auto-generated schematic symbols\n")
            for line in lines:
                if line != None:
                    f.write(line + "\n")

        print(f"✅ Exported {len(lines)} symbols to {self.output_path}")

        return lines

    
    def build_mapping(self):
        """
        Build the mapping of symbol libraries to their full names.
        This is a placeholder function and should be implemented based on the actual library structure.
        """
        # Get the location map from symbols, labels and wires to locations
        for component in self.schematic.symbol:

            reference = component.Reference.value if hasattr(component, "Reference") else ""
            # If the component belongs to single pin symbol
            if isinstance(component.pin, my_skip_lib.sexp.parser.ParsedValue):
                pin_pos = component.pin.parent.at.value[:2]
                self.pin_location_map[tuple(pin_pos)] = (reference, "1") # If only one pin, use "1", for example, GND, VCC symbols.
                self.pin_location_name_map[tuple(pin_pos)] = (reference, component.Value.value if hasattr(component.Value, "value") else "nan")
            # If the component has multiple pins
            else:
                for pin in component.pin: 
                    if isinstance(pin, my_skip_lib.eeschema.schematic.symbol.SymbolPin):
                        self.pin_location_map[tuple(pin.location.value[:2])] = (reference, pin.number)
                        # If a connector symbol, we don't use names due to issue when manually edit the schematic files. 
                        if hasattr(component.Value, "value") and "Conn" not in component.Value.value:
                            self.pin_location_name_map[tuple(pin.location.value[:2])] = (reference, pin.name)
                        else:
                            self.pin_location_name_map[tuple(pin.location.value[:2])] = (reference, "nan")

        label_text_ct = {}  # To ensure unique label IDs
        
        for label in self.schematic.global_label:
            # TODO: handle net labels as well

            label_text = label.value if hasattr(label, "value") else label.value

            # 2. label_type
            # label_type = label.shape.value if hasattr(label, "shape") else "input"

            # 3. label_pos (x, y)
            at = label.at.value if hasattr(label.at, "value") else label.at
            label_pos = [float(at[0]), float(at[1]), float(at[2])] if len(at) > 2 else [float(at[0]), float(at[1]), 0.0]

            if label_text not in label_text_ct:
                label_text_ct[label_text] = 0
            else:
                label_text_ct[label_text] += 1

            self.label_location_map[tuple(label_pos[:2])] = (label_text, f"{label_text_ct[label_text]}")


        # Build the connection graph from the wires
        for wire in self.schematic.wire:
            start = tuple(wire.start.value)
            end = tuple(wire.end.value)
            self.wire_location_map[tuple([start, end])] = wire
            self.wire_location_map[tuple([end, start])] = wire
            self.global_conn_graph[start].add(end)
            self.global_conn_graph[end].add(start)
        
        # This is a map from "point coordinates" to (symbol reference, symbol pin name)
        self.all_points_map = {**self.pin_location_map, **self.label_location_map}

from modules.kicad_sch_interface import get_project_path
from pathlib import Path


import os
from pathlib import Path

sch_pattern = re.compile(r"^sch_(\d+)_(\d+)\.kicad_sch$", re.IGNORECASE)
block_pattern = re.compile(r"^block[_\-]?\d+\.kicad_sch$", re.IGNORECASE)

# Debug trigger: 1
DEBUG = 0

def debug():

    sch_path = proj_path / "dataset/15335_9DoF_Schematic/block_4.kicad_sch"
    stem = sch_path.stem
    module_name = sch_path.parent.name
    out_py = sch_path.parent / f"{stem}_int.py"

    generator = code_generator(
        module_name=module_name,
        sch_ref_path=str(sch_path),
        output_path=str(out_py),
    )
    print(
        f"✅ [{module_name}/{sch_path.name}] "
        f"Loaded {len(generator.pin_location_map)} pins, "
        f"{len(generator.label_location_map)} labels, "
        f"and {len(generator.wire_location_map)} wires."
    )

    generator.work()

if __name__ == "__main__":

    def run_single(module_name, sch_ref_path, repr_level):
        # Set the global representation level used by the generator
        global code_representation_level
        code_representation_level = repr_level

        out_p = Path(sch_ref_path)
        final_out = out_p.parent / f"{out_p.stem}_{repr_level}.py"

        generator = code_generator(
            module_name=module_name,
            sch_ref_path=sch_ref_path,
            output_path=str(final_out),
        )
        print(
            f"✅ [{module_name}/{Path(sch_ref_path).name}] "
            f"Loaded {len(generator.pin_location_map)} pins, "
            f"{len(generator.label_location_map)} labels, "
            f"and {len(generator.wire_location_map)} wires."
        )

        generator.work()

    parser = argparse.ArgumentParser(description="Generate schematic code from KiCad schematic files.")
    parser.add_argument("-m", "--module", dest="module", type=str, help="Module name for the schematic")
    parser.add_argument("-s", "--sch", dest="sch", type=str, help="Path to the reference schematic")
    parser.add_argument("-r", "--repr", dest="repr", type=str, default=code_representation_level, help="Representation level: L1 (default), L2, or L3")
    parser.add_argument("--debug", action="store_true", help="Run the built-in debug example")
    args = parser.parse_args()

    if args.module and args.sch:
        run_single(args.module, args.sch, args.repr)
        sys.exit(0)

    if args.debug or DEBUG:
        debug()
    else:
        proj_path = Path(os.environ["PROJECT_PATH"])
        base_dir = proj_path / "dataset"

        if not base_dir.exists():
            raise FileNotFoundError(f"[Error] Base dir not found: {base_dir}")

        total_files = 0
        ok_files = 0
        skipped_files = 0
        failed_files = 0

        for module_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
            module_name = module_dir.name
            print(f"\nProcessing module: {module_name}")

            for sch_path in sorted(module_dir.glob("sch_*_*.kicad_sch")):
                total_files += 1

                if sch_path.name.endswith("_out.kicad_sch"):
                    skipped_files += 1
                    continue

                if not sch_pattern.match(sch_path.name):

                    skipped_files += 1
                    continue

                stem = sch_path.stem  
                out_py = module_dir / f"{stem}_{code_representation_level}.py"

                try:
                    pass
                    generator = code_generator(
                        module_name=module_name,
                        sch_ref_path=str(sch_path),
                        output_path=str(out_py),
                    )
                    print(
                        f"✅ [{module_name}/{sch_path.name}] "
                        f"Loaded {len(generator.pin_location_map)} pins, "
                        f"{len(generator.label_location_map)} labels, "
                        f"and {len(generator.wire_location_map)} wires."
                    )

                    generator.work()
                    ok_files += 1

                except Exception as e:
                    failed_files += 1
                    print(f"❌ [{module_name}/{sch_path.name}] Failed: {e}")

        print(
            f"\nSummary: total={total_files}, ok={ok_files}, skipped={skipped_files}, failed={failed_files}"
        )