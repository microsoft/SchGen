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
# Add label FSYNC
add_label(label_pos=[135.89, 94.43], label_text="FSYNC", label_ref="FSYNC_0", label_type="input", text_orient="left")
# Add label CS
add_label(label_pos=[135.89, 99.51], label_text="CS", label_ref="CS_0", label_type="input", text_orient="left")
# Add label SCL{slash}SCLK
add_label(label_pos=[135.89, 102.05], label_text="SCL{slash}SCLK", label_ref="SCL{slash}SCLK_0", label_type="input", text_orient="left")
# Add label SDA{slash}SDI
add_label(label_pos=[135.89, 104.59], label_text="SDA{slash}SDI", label_ref="SDA{slash}SDI_0", label_type="input", text_orient="left")
# Add label AD0{slash}SDO
add_label(label_pos=[135.89, 107.13], label_text="AD0{slash}SDO", label_ref="AD0{slash}SDO_0", label_type="input", text_orient="left")
# Add label AUX_CL
add_label(label_pos=[182.88, 99.51], label_text="AUX_CL", label_ref="AUX_CL_0", label_type="input", text_orient="right")
# Add label AUX_DA
add_label(label_pos=[182.88, 102.05], label_text="AUX_DA", label_ref="AUX_DA_0", label_type="input", text_orient="right")

### Adding all wires in the Schematic ###

add_new_wire([99.06, 117.29], [99.06, 99.51])
add_new_wire([157.48, 81.73], [157.48, 79.19])
add_new_wire([135.89, 91.89], [144.78, 91.89])
add_new_wire([135.89, 94.43], [144.78, 94.43])
add_new_wire([135.89, 104.59], [144.78, 104.59])
add_new_wire([175.26, 94.43], [175.26, 93.16])
add_new_wire([170.18, 102.05], [182.88, 102.05])
add_new_wire([114.3, 117.29], [154.94, 117.29])
add_new_wire([135.89, 102.05], [144.78, 102.05])
add_new_wire([114.3, 99.51], [114.3, 117.29])
add_new_wire([154.94, 117.29], [160.02, 117.29])
add_new_wire([114.3, 91.89], [114.3, 85.54])
add_new_wire([135.89, 107.13], [144.78, 107.13])
add_new_wire([175.26, 85.54], [175.26, 75.38])
add_new_wire([170.18, 99.51], [182.88, 99.51])
add_new_wire([170.18, 94.43], [175.26, 94.43])
add_new_wire([99.06, 91.89], [99.06, 85.54])
add_new_wire([99.06, 117.29], [114.3, 117.29])
add_new_wire([135.89, 99.51], [144.78, 99.51])

write_out_all_wires()
