# Auto-generated schematic symbols
import sys
import os

# Get project path and import kicad schematic interface
PROJECT_PATH = os.environ['PROJECT_PATH']
sys.path.append(PROJECT_PATH)
from modules.kicad_sch_interface import *

### Placing center symbol 1 : Transistor_FET:BSS138###

center_x_1, center_y_1 = 150.0, 110.0

add_schematic_symbol(symbol_lib="Transistor_FET", symbol_name="BSS138", pos_x=center_x_1, pos_y=center_y_1, reference="Q2", value="BSS138", rotation=270, mirror="None")

### Placing other symbols in the Schematic with respect to the center symbol 1###

add_schematic_symbol(symbol_lib="power", symbol_name="+1V8", pos_x=center_x_1 + (-72), pos_y=center_y_1 + (22), reference="#PWR1", value="+1V8", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="R", pos_x=center_x_1 + (-72), pos_y=center_y_1 + (8), reference="R1", value="2.2K", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Transistor_FET", symbol_name="BSS138", pos_x=center_x_1 + (-62), pos_y=center_y_1 + (0), reference="Q1", value="BSS138", rotation=270, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="R", pos_x=center_x_1 + (-53), pos_y=center_y_1 + (8), reference="R2", value="2.2K", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="VAA", pos_x=center_x_1 + (-31), pos_y=center_y_1 + (22), reference="#PWR2", value="VIN", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Jumper", symbol_name="SolderJumper_3_Bridged123", pos_x=center_x_1 + (-31), pos_y=center_y_1 + (15), reference="JP1", value="AUX", rotation=0, mirror="x")
add_schematic_symbol(symbol_lib="power", symbol_name="+1V8", pos_x=center_x_1 + (-8), pos_y=center_y_1 + (22), reference="#PWR3", value="+1V8", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="R", pos_x=center_x_1 + (-8), pos_y=center_y_1 + (8), reference="R3", value="2.2K", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="R", pos_x=center_x_1 + (10), pos_y=center_y_1 + (8), reference="R4", value="2.2K", rotation=0, mirror="None")

### Placing all global labels in the Schematic and connect them to the neighbor pin ###

# Add label AUX_DA next to Q1 pin S 
x_Q1_2, y_Q1_2 = get_pin_location(symbol_ref="Q1", pin_name="S")
add_label(label_pos=[x_Q1_2+(-13), y_Q1_2+(0)], label_text="AUX_DA", label_ref="AUX_DA_0", label_type="input", text_orient="left")
# Connecting Label AUX_DA label_id:0 to Q1 pin S (Pin ID 2 -- Name S)
connect_pins("AUX_DA_0", "1", "Q1", "S")

# Add label AUX_DA_VIN next to Q1 pin D 
x_Q1_3, y_Q1_3 = get_pin_location(symbol_ref="Q1", pin_name="D")
add_label(label_pos=[x_Q1_3+(6), y_Q1_3+(0)], label_text="AUX_DA_VIN", label_ref="AUX_DA_VIN_0", label_type="input", text_orient="right")
# Connecting Label AUX_DA_VIN label_id:0 to Q1 pin D (Pin ID 3 -- Name D)
connect_pins("AUX_DA_VIN_0", "1", "Q1", "D")

# Add label AUX_CL next to Q2 pin S 
x_Q2_2, y_Q2_2 = get_pin_location(symbol_ref="Q2", pin_name="S")
add_label(label_pos=[x_Q2_2+(-12), y_Q2_2+(0)], label_text="AUX_CL", label_ref="AUX_CL_0", label_type="input", text_orient="left")
# Connecting Label AUX_CL label_id:0 to Q2 pin S (Pin ID 2 -- Name S)
connect_pins("AUX_CL_0", "1", "Q2", "S")

# Add label AUX_CL_VIN next to Q2 pin D 
x_Q2_3, y_Q2_3 = get_pin_location(symbol_ref="Q2", pin_name="D")
add_label(label_pos=[x_Q2_3+(17), y_Q2_3+(0)], label_text="AUX_CL_VIN", label_ref="AUX_CL_VIN_0", label_type="input", text_orient="right")
# Connecting Label AUX_CL_VIN label_id:0 to Q2 pin D (Pin ID 3 -- Name D)
connect_pins("AUX_CL_VIN_0", "1", "Q2", "D")


### Connecting all wires in the Schematic ###


# Connecting #PWR2 pin VIN (Pin ID 1 -- Name VIN) to JP1 pin C (Pin ID 2 -- Name C)
connect_pins("#PWR2", "VIN", "JP1", "C")

# Connecting #PWR1 pin +1V8 (Pin ID 1 -- Name +1V8) to R1 pin 1 (Pin ID 1 -- Name None)
connect_pins("#PWR1", "+1V8", "R1", "1")

# Connecting #PWR3 pin +1V8 (Pin ID 1 -- Name +1V8) to R3 pin 1 (Pin ID 1 -- Name None)
connect_pins("#PWR3", "+1V8", "R3", "1")

# Connecting Q1 pin D (Pin ID 3 -- Name D) to R2 pin 2 (Pin ID 2 -- Name None)
connect_pins("Q1", "D", "R2", "2")

# Connecting R3 pin 2 (Pin ID 2 -- Name None) to Q2 pin S (Pin ID 2 -- Name S)
connect_pins("R3", "2", "Q2", "S")

# Connecting Q2 pin D (Pin ID 3 -- Name D) to R4 pin 2 (Pin ID 2 -- Name None)
connect_pins("Q2", "D", "R4", "2")

# Connecting R1 pin 2 (Pin ID 2 -- Name None) to Q1 pin S (Pin ID 2 -- Name S)
connect_pins("R1", "2", "Q1", "S")

# Connecting R3 pin 1 (Pin ID 1 -- Name None) to Q2 pin G (Pin ID 1 -- Name G)
connect_pins("R3", "1", "Q2", "G")

# Connecting R2 pin 1 (Pin ID 1 -- Name None) to JP1 pin A (Pin ID 1 -- Name A)
connect_pins("R2", "1", "JP1", "A")

# Connecting R1 pin 1 (Pin ID 1 -- Name None) to Q1 pin G (Pin ID 1 -- Name G)
connect_pins("R1", "1", "Q1", "G")

# Connecting JP1 pin B (Pin ID 3 -- Name B) to R4 pin 1 (Pin ID 1 -- Name None)
connect_pins("JP1", "B", "R4", "1")

write_out_all_wires()
