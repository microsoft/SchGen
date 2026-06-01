import sys
import os

# Get project path and import kicad schematic interface
PROJECT_PATH = os.environ["PROJECT_PATH"]
sys.path.append(PROJECT_PATH)
from modules.kicad_sch_interface import *

# -----------------------------------------------------------------------------
# 3.3V regulator block based on AP2112K (symbol unavailable in provided context)
# Implemented using ONLY the allowed symbols:
#   - Device:C
#   - power:+5V
#   - power:+3.3V
#   - power:GND
# U1 is represented as a placeholder using Device:C with value "AP2112".
# -----------------------------------------------------------------------------

# Keep the block centered on an A4 sheet (210 x 297mm)
center_x, center_y = 105.0, 160.0

# --- Place the central "U1" placeholder ---
add_schematic_symbol(
    symbol_lib="Device",
    symbol_name="C",
    pos_x=center_x,
    pos_y=center_y,
    reference="U1",
    value="AP2112",
    rotation=0,
    mirror=None,
)

# --- Place input/output capacitors (C1 left, C2 right) ---
add_schematic_symbol(
    symbol_lib="Device",
    symbol_name="C",
    pos_x=center_x - 40.0,
    pos_y=center_y,
    reference="C1",
    value="1uF",
    rotation=0,
    mirror=None,
)

add_schematic_symbol(
    symbol_lib="Device",
    symbol_name="C",
    pos_x=center_x + 40.0,
    pos_y=center_y,
    reference="C2",
    value="1uF",
    rotation=0,
    mirror=None,
)

# --- Power symbols above rails ---
add_schematic_symbol(
    symbol_lib="power",
    symbol_name="+5V",
    pos_x=center_x - 40.0,
    pos_y=center_y + 18.0,
    reference="#PWR1",
    value="+5V",
    rotation=0,
    mirror=None,
)

add_schematic_symbol(
    symbol_lib="power",
    symbol_name="+3.3V",
    pos_x=center_x + 40.0,
    pos_y=center_y + 18.0,
    reference="#PWR2",
    value="+3.3V",
    rotation=0,
    mirror=None,
)

# --- GND symbols under each capacitor and under the center block ---
add_schematic_symbol(
    symbol_lib="power",
    symbol_name="GND",
    pos_x=center_x - 40.0,
    pos_y=center_y - 18.0,
    reference="#PWR3",
    value="GND",
    rotation=0,
    mirror=None,
)

add_schematic_symbol(
    symbol_lib="power",
    symbol_name="GND",
    pos_x=center_x + 40.0,
    pos_y=center_y - 18.0,
    reference="#PWR4",
    value="GND",
    rotation=0,
    mirror=None,
)

add_schematic_symbol(
    symbol_lib="power",
    symbol_name="GND",
    pos_x=center_x,
    pos_y=center_y - 22.0,
    reference="#PWR5",
    value="GND",
    rotation=0,
    mirror=None,
)

# --- Connectivity (using only valid pin names from the allowed context) ---
# Input rail: +5V -> C1 top (pin 1) and -> U1 placeholder pin 1
connect_pins("#PWR1", "1", "C1", "1")
connect_pins("#PWR1", "1", "U1", "1")

# Output rail: +3.3V -> C2 top (pin 1) and -> U1 placeholder pin 2
connect_pins("#PWR2", "1", "C2", "1")
connect_pins("#PWR2", "1", "U1", "2")

# Grounds: capacitor bottoms (pin 2) to GND symbols
connect_pins("C1", "2", "#PWR3", "1")
connect_pins("C2", "2", "#PWR4", "1")

# Optional: tie the center GND symbol into the same drawn ground wiring (not required
# electrically since all GND symbols share the same global net name, but helps layout)
connect_pins("#PWR5", "1", "#PWR3", "1")

write_out_all_wires()
