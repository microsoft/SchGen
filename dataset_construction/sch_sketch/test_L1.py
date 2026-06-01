# Auto-generated schematic symbols
import sys
import os

# Get project path and import kicad schematic interface
PROJECT_PATH = os.environ['PROJECT_PATH']
sys.path.append(PROJECT_PATH)
from modules.kicad_sch_interface import *

### Placing center symbol 1 : Regulator_Linear:AP2112K-3.3###

center_x_1, center_y_1 = 150.0, 110.0

add_schematic_symbol(symbol_lib="Regulator_Linear", symbol_name="AP2112K-3.3", pos_x=center_x_1, pos_y=center_y_1, reference="U1", value="AP2112K-3.3", rotation=0, mirror="None")

### Placing other symbols in the Schematic with respect to the center symbol 1###

add_schematic_symbol(symbol_lib="power", symbol_name="+5V", pos_x=center_x_1 + (-40), pos_y=center_y_1 + (13), reference="#PWR1", value="+5V", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="C", pos_x=center_x_1 + (-40), pos_y=center_y_1 + (-1), reference="C1", value="1uF", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=center_x_1 + (-40), pos_y=center_y_1 + (-15), reference="#PWR3", value="GND", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=center_x_1 + (0), pos_y=center_y_1 + (-17), reference="#PWR4", value="GND", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="+3.3V", pos_x=center_x_1 + (39), pos_y=center_y_1 + (13), reference="#PWR2", value="+3.3V", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="Device", symbol_name="C", pos_x=center_x_1 + (39), pos_y=center_y_1 + (-1), reference="C2", value="1uF", rotation=0, mirror="None")
add_schematic_symbol(symbol_lib="power", symbol_name="GND", pos_x=center_x_1 + (39), pos_y=center_y_1 + (-15), reference="#PWR5", value="GND", rotation=0, mirror="None")

### Placing all global labels in the Schematic and connect them to the neighbor pin ###


### Connecting all wires in the Schematic ###


# Connecting U1 pin 2 (Pin ID 2 -- Name None) to #PWR4 pin 1 (Pin ID 1 -- Name None)
connect_pins("U1", "2", "#PWR4", "1")

# Connecting C2 pin 2 (Pin ID 2 -- Name None) to #PWR5 pin 1 (Pin ID 1 -- Name None)
connect_pins("C2", "2", "#PWR5", "1")

# Connecting C1 pin 2 (Pin ID 2 -- Name None) to #PWR3 pin 1 (Pin ID 1 -- Name None)
connect_pins("C1", "2", "#PWR3", "1")

# Connecting #PWR2 pin +3.3V (Pin ID 1 -- Name +3.3V) to C2 pin 1 (Pin ID 1 -- Name None)
connect_pins("#PWR2", "+3.3V", "C2", "1")

# Connecting #PWR1 pin +5V (Pin ID 1 -- Name +5V) to C1 pin 1 (Pin ID 1 -- Name None)
connect_pins("#PWR1", "+5V", "C1", "1")

# Connecting C1 pin 1 (Pin ID 1 -- Name None) to U1 pin VIN (Pin ID 1 -- Name VIN)
connect_pins("C1", "1", "U1", "VIN")

# Connecting U1 pin VOUT (Pin ID 5 -- Name VOUT) to #PWR2 pin +3.3V (Pin ID 1 -- Name +3.3V)
connect_pins("U1", "VOUT", "#PWR2", "+3.3V")

# Connecting #PWR1 pin +5V (Pin ID 1 -- Name +5V) to U1 pin EN (Pin ID 3 -- Name EN)
connect_pins("#PWR1", "+5V", "U1", "EN")

write_out_all_wires()
