# Auto-generated schematic symbols
import sys
import os

# Get project path and import kicad schematic interface
PROJECT_PATH = os.environ['PROJECT_PATH']
sys.path.append(PROJECT_PATH)
from modules.kicad_sch_interface import *

### Placing center symbol 1 : Sensor_Motion:ICM-20948###

center_x_1, center_y_1 = 157.480, 99.510

add_schematic_symbol(symbol_lib="Sensor_Motion", symbol_name="ICM-20948", pos_x=center_x_1, pos_y=center_y_1, reference="U2", value="ICM-20948", rotation=0, mirror="None")

### Placing other symbols in the Schematic with respect to the center symbol 1###

add_schematic_symbol(symbol_lib="power", symbol_name="+1V8", pos_x=99.06, pos_y=117.29, reference="#PWR1", value="+1V8", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="C", pos_x=99.06, pos_y=95.7, reference="C1", value="1uF", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=99.06, pos_y=85.54, reference="#PWR_C1", value="GND", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="C", pos_x=114.3, pos_y=95.7, reference="C2", value="100nF", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=114.3, pos_y=85.54, reference="#PWR_C2", value="GND", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=157.48, pos_y=79.19, reference="#PWR_C4", value="GND", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="C", pos_x=175.26, pos_y=89.35, reference="C3", value="100nF", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=175.26, pos_y=75.38, reference="#PWR_C3", value="GND", rotation=0, mirror="None")

### Placing all global labels in the Schematic and connect them to the neighbor pin ###

# Add label INT
add_label(label_pos=[135.89, 91.89], label_text="INT", label_ref="INT_0", label_type="input", text_orient="left")
# Connecting Label INT label_id:0 to U2 pin INT1 (Pin ID 12 -- Name INT1)
connect_pins("INT_0", "1", "U2", "INT1")

# Add label FSYNC
add_label(label_pos=[135.89, 94.43], label_text="FSYNC", label_ref="FSYNC_0", label_type="input", text_orient="left")
# Connecting Label FSYNC label_id:0 to U2 pin FSYNC (Pin ID 11 -- Name FSYNC)
connect_pins("FSYNC_0", "1", "U2", "FSYNC")

# Add label CS
add_label(label_pos=[135.89, 99.51], label_text="CS", label_ref="CS_0", label_type="input", text_orient="left")
# Connecting Label CS label_id:0 to U2 pin ~{CS} (Pin ID 22 -- Name ~{CS})
connect_pins("CS_0", "1", "U2", "~{CS}")

# Add label SCL{slash}SCLK
add_label(label_pos=[135.89, 102.05], label_text="SCL{slash}SCLK", label_ref="SCL{slash}SCLK_0", label_type="input", text_orient="left")
# Connecting Label SCL{slash}SCLK label_id:0 to U2 pin SCL/SCLK (Pin ID 23 -- Name SCL/SCLK)
connect_pins("SCL{slash}SCLK_0", "1", "U2", "SCL/SCLK")

# Add label SDA{slash}SDI
add_label(label_pos=[135.89, 104.59], label_text="SDA{slash}SDI", label_ref="SDA{slash}SDI_0", label_type="input", text_orient="left")
# Connecting Label SDA{slash}SDI label_id:0 to U2 pin SDA/SDI (Pin ID 24 -- Name SDA/SDI)
connect_pins("SDA{slash}SDI_0", "1", "U2", "SDA/SDI")

# Add label AD0{slash}SDO
add_label(label_pos=[135.89, 107.13], label_text="AD0{slash}SDO", label_ref="AD0{slash}SDO_0", label_type="input", text_orient="left")
# Connecting Label AD0{slash}SDO label_id:0 to U2 pin SDO/AD0 (Pin ID 9 -- Name SDO/AD0)
connect_pins("AD0{slash}SDO_0", "1", "U2", "SDO/AD0")

# Add label AUX_CL
add_label(label_pos=[182.88, 99.51], label_text="AUX_CL", label_ref="AUX_CL_0", label_type="input", text_orient="right")
# Connecting Label AUX_CL label_id:0 to U2 pin AUX_CL (Pin ID 7 -- Name AUX_CL)
connect_pins("AUX_CL_0", "1", "U2", "AUX_CL")

# Add label AUX_DA
add_label(label_pos=[182.88, 102.05], label_text="AUX_DA", label_ref="AUX_DA_0", label_type="input", text_orient="right")
# Connecting Label AUX_DA label_id:0 to U2 pin AUX_DA (Pin ID 21 -- Name AUX_DA)
connect_pins("AUX_DA_0", "1", "U2", "AUX_DA")


### Connecting all wires in the Schematic ###


# Connecting U2 pin 20 (Pin ID 20 -- Name None) to #PWR_C4 pin 1 (Pin ID 1 -- Name None)
connect_pins("U2", "20", "#PWR_C4", "1")

# Connecting U2 pin VDDIO (Pin ID 8 -- Name VDDIO) to U2 pin VDD (Pin ID 13 -- Name VDD)
connect_pins("U2", "VDDIO", "U2", "VDD")

# Connecting C1 pin 2 (Pin ID 2 -- Name None) to #PWR_C1 pin 1 (Pin ID 1 -- Name None)
connect_pins("C1", "2", "#PWR_C1", "1")

# Connecting C2 pin 2 (Pin ID 2 -- Name None) to #PWR_C2 pin 1 (Pin ID 1 -- Name None)
connect_pins("C2", "2", "#PWR_C2", "1")

# Connecting U2 pin REGOUT (Pin ID 10 -- Name REGOUT) to C3 pin 1 (Pin ID 1 -- Name None)
connect_pins("U2", "REGOUT", "C3", "1")

# Connecting C3 pin 2 (Pin ID 2 -- Name None) to #PWR_C3 pin 1 (Pin ID 1 -- Name None)
connect_pins("C3", "2", "#PWR_C3", "1")

# Connecting #PWR1 pin +1V8 (Pin ID 1 -- Name +1V8) to C1 pin 1 (Pin ID 1 -- Name None)
connect_pins("#PWR1", "+1V8", "C1", "1")

# Connecting #PWR1 pin +1V8 (Pin ID 1 -- Name +1V8) to C2 pin 1 (Pin ID 1 -- Name None)
connect_pins("#PWR1", "+1V8", "C2", "1")

# Connecting #PWR1 pin +1V8 (Pin ID 1 -- Name +1V8) to U2 pin VDDIO (Pin ID 8 -- Name VDDIO)
connect_pins("#PWR1", "+1V8", "U2", "VDDIO")

write_out_all_wires()
