# MUST import the functions from the modules to get APIs
from modules.kicad_sch_interface import *

# -------------------------------------------------------------
# Helper: place a global label safely outside a symbol           
# -------------------------------------------------------------
Center_X = 150
Center_Y = 100
Offset_Unit = 5  # offset unit for label placement


def place_label_on_pin(sym_ref: str, pin_name: str, label: str, extra_dx: int = 0, label_type="bidirectional"):
    """Attach LABEL to *pin_name* of *sym_ref* and keep the text outside
       the symbol body.  extra_dx enlarges the gap if desired."""
    x_pin, _ = get_pin_location(sym_ref, pin_name)

    sym_center_x, _ = get_symbol_location(sym_ref)

    if x_pin < sym_center_x:                     # pins on the left edge
        dx = -Offset_Unit - abs(extra_dx)
    elif x_pin > sym_center_x:                   # pins on the right edge
        dx =  Offset_Unit + abs(extra_dx)
    else:                               # centre-line pins (top / bottom rows)
        dx = -Offset_Unit - abs(extra_dx)
    connect_pin_to_label(sym_ref, pin_name, label, dx, label_type=label_type)


# -------------------------------------------------------------
# 1) ESP32-S3 module (centre of sheet)                          
# -------------------------------------------------------------
add_schematic_symbol("RF_Module", "ESP32-S3-WROOM-1", Center_X, Center_Y,
                     reference="U1", value="ESP32-S3-WROOM-1")


#  Label all the IO pins that connect to labels that have the same name
for io_id in list(range(0, 18)) + list(range(35, 38)) + [21, 45, 46, 47, 48]:
    pin_name = f"IO{io_id}"

    # Connect the pin to a label with the same name
    place_label_on_pin("U1", pin_name, pin_name)


# Connect other pins with special names to labels
for pin, lbl in [ 
        ("EN", "EN"), ("TXD0", "TXD0"), ("RXD0", "RXD0"),
        ("USB_D-", "USB_D-"), ("USB_D+", "USB_D+"),
        ("IO42", "TMS"), ("IO41", "TDI"),
        ("IO40", "TDO"), ("IO39", "TCK")
    ]:
    place_label_on_pin("U1", pin, lbl)


# Connect power pins to power symbols
# GND pin to GND power symbol
u1_gnd_x, u1_gnd_y = get_pin_location("U1", "GND")
add_power_symbol("GND", "#PWR_GND_U1", u1_gnd_x, u1_gnd_y-Offset_Unit)
add_new_wire([u1_gnd_x, u1_gnd_y], [u1_gnd_x, u1_gnd_y-Offset_Unit])
# 3.3-V pin to VDD33 power symbol
u1_vdd_x, u1_vdd_y = get_pin_location("U1", "3V3")
add_power_symbol("+3.3V", "#PWR_3V3", u1_vdd_x, u1_vdd_y+Offset_Unit)
add_new_wire([u1_vdd_x, u1_vdd_y], [u1_vdd_x, u1_vdd_y+Offset_Unit])


# -------------------------------------------------------------
# 2) 3.3-V rail & decoupling                       
# -------------------------------------------------------------
# put the power symbol at the upper left corner of the sheet
vdd_x_pos = Center_X - 70 # ESP32 X size is 20mm, considering labels will take another 10mm, so we need to shift to get space.
vdd_y_pos = Center_Y + 20
add_power_symbol("+3.3V", "#PWR_VDD", vdd_x_pos, vdd_y_pos)

for cap_x_pos, ref, val in [(vdd_x_pos, "C1", "22uF"), (vdd_x_pos+10, "C3", "100nF")]:
    # add a decoupling capacitor and GND associated with it
    add_RLC_symbol("C", cap_x_pos, vdd_y_pos-10, ref, val)                  # top → VDD33
    add_power_symbol("GND", f"#PWR_{ref}", *get_pin_location(ref, "2"))

# Connect the decoupling capacitors to the VDD33 rail
cap1_p1_x, cap1_p1_y = get_pin_location("C1", "1")
cap3_p1_x, cap3_p1_y = get_pin_location("C3", "1")
add_new_wire([vdd_x_pos, vdd_y_pos], [cap1_p1_x, cap1_p1_y])  # VDD33 to C1 pin 1
add_new_wire([cap1_p1_x, cap1_p1_y], [cap3_p1_x, cap3_p1_y])  # C1 to C3 to share the VDD pin.



# # -------------------------------------------------------------
# 3) EN pull-up RC delay circuit.
#  The recommended setting for the RC delay circuit is usually R = 10 kΩ and C = 1 µF             
# However, specific parameters should be adjusted based on the power-up timing of the module and the power-up and reset sequence timing of the chip. -- See datasheet.
# # -------------------------------------------------------------
add_RLC_symbol("R", vdd_x_pos +20, vdd_y_pos-10, "R1", "10K")                   # pull-up resistor
add_RLC_symbol("C", vdd_x_pos +20, vdd_y_pos-20, "C2", "1uF")                   # delay capacitor for stability

# Connect R1-1 with VDD33 rail
add_new_wire(get_pin_location("R1", "1"), [cap3_p1_x, cap3_p1_y])  # R1-1 to VDD33 rail (C3-1 is the closest point)
# Connect R and C
add_new_wire(get_pin_location("R1", "2"), get_pin_location("C2", "1"))  # R1-2 to C2-1
# add EN label
connect_pin_to_label("R1", "2", "EN", 5, label_type="bidirectional")  # R1-2 to EN label
# add GND power symbol for the capacitor
add_power_symbol("GND", "#PWR_C2", *get_pin_location("C2", "2"))


# # -------------------------------------------------------------
# # 3) Reset / EN push-button filter                              
# # -------------------------------------------------------------

# Add switch and filter capacitor and 0-Ω link
switch_pos_x, switch_pos_y = Center_X + 50, Center_Y -30 
add_schematic_symbol("Switch", "SW_Push", switch_pos_x, switch_pos_y, "SW1", "SW_Push")
add_RLC_symbol("R", switch_pos_x+10, switch_pos_y, "R7", "0", rotation=270)    # 0-Ω link, rotated by 270 degrees counter-clockwise
add_RLC_symbol("C", switch_pos_x, switch_pos_y-10, "C8", "100nF", rotation=270)  # filter cap

# position a new EN label next to the R7 symbol
place_label_on_pin("R7", "1", "EN", extra_dx=5, label_type="bidirectional")  # R7-1 to EN label

# Connect wires
add_new_wire(get_pin_location("SW1", "2"), get_pin_location("R7", "2"))  # SW1-1 to R7-2
draw_manhattan_wire(get_pin_location("C8", "1"), get_pin_location("SW1", "2"), bent_down=True)  # C8-1 to SW1-2 (horizontal then vertical)

# Add GND power symbol for the capacitor and switch
sw_p1_x, sw_p1_y = get_pin_location("SW1", "1")
add_power_symbol("GND", "#PWR_SW", sw_p1_x, sw_p1_y-20)  # SW1-2 GND
# Connect the switch to GND power symbol
add_new_wire(get_pin_location("SW1", "1"), get_pin_location("#PWR_SW", "1"))  # SW1-1 to GND power symbol
# Connect C8 to GND power symbol
draw_manhattan_wire(get_pin_location("C8", "2"), get_pin_location("#PWR_SW", "1"), bent_down=False)  # C8-2 to GND power symbol

# # -------------------------------------------------------------
# # 4) 32-kHz crystal network  -- SKIP, as it is NC (no component) in this datasheet schematic   
# # -------------------------------------------------------------


# # -------------------------------------------------------------
# # 5) USB-OTG connector + series & shunt parts                   
# # -------------------------------------------------------------
USB_conn_x, USB_conn_y = Center_X - 70, Center_Y - 20
add_schematic_symbol("Connector_Generic", "Conn_01x02", USB_conn_x, USB_conn_y, "JP3", "USB_OTG")
move_symbol("JP3", 0, 0, rotation=180)  # rotate so pins face right

conn_p1_x, conn_p1_y = get_pin_location("JP3", "1")
conn_p2_x, conn_p2_y = get_pin_location("JP3", "2")

add_RLC_symbol("R", USB_conn_x + 15, conn_p1_y, "R6", "0", rotation=90)
add_RLC_symbol("R", USB_conn_x + 15, conn_p2_y, "R4", "0", rotation=90)
connect_pin_to_label("R6", "2", "USB_D-", 6)  # D- series resistor
connect_pin_to_label("R4", "2", "USB_D+", 6)  # D+ series resistor
add_new_wire(get_pin_location("JP3", "1"), get_pin_location("R6", "1"))  # JP3-1 to R6-1
add_new_wire(get_pin_location("JP3", "2"), get_pin_location("R4", "1"))  # JP3-2 to R4-1

add_RLC_symbol("C", USB_conn_x+5, USB_conn_y-10, "C6", "1nF")
add_RLC_symbol("C", USB_conn_x+10, USB_conn_y-10, "C5", "1nF")
add_power_symbol("GND", "#PWR_C5", *get_pin_location("C5", "2"))  # GND for C5
add_power_symbol("GND", "#PWR_C6", *get_pin_location("C6", "2"))  # GND for C6

draw_manhattan_wire(get_pin_location("JP3", "1"), get_pin_location("C6", "1"), bent_down=False)  # JP3-1 to R6-1
draw_manhattan_wire(get_pin_location("JP3", "2"), get_pin_location("C5", "1"), bent_down=False)  # JP3-2 to R4-1

# # -------------------------------------------------------------
# # 6) UART header (GND-VDD-RX-TX)                                
# # -------------------------------------------------------------
UART_conn_x, UART_conn_y = Center_X + 60, Center_Y + 20
add_schematic_symbol("Connector_Generic", "Conn_01x04", UART_conn_x, UART_conn_y, "JP1", "UART")
jp1_p1_x, jp1_p1_y = get_pin_location("JP1", "1")  # VDD33
add_new_wire([jp1_p1_x, jp1_p1_y], [jp1_p1_x, jp1_p1_y+5])  # VDD33 to VDD33 power symbol
add_power_symbol("+3.3V", "#PWR_VDD_JP1", jp1_p1_x, jp1_p1_y+5)  # VDD33 power symbol
place_label_on_pin("JP1", "2", "RXD0",  5)
place_label_on_pin("JP1", "3", "TXD0",  5)
jp1_p4_x, jp1_p4_y = get_pin_location("JP1", "4")  # GND
add_new_wire([jp1_p4_x, jp1_p4_y], [jp1_p4_x, jp1_p4_y-5])  # VDD33 to GND
add_power_symbol("GND", "#PWR_GND_JP1", jp1_p4_x, jp1_p4_y-5)  # GND power symbol

# # -------------------------------------------------------------
# # 7) JTAG header                                               
# # -------------------------------------------------------------
JTAG_conn_x, JTAG_conn_y = Center_X + 60, Center_Y 
add_schematic_symbol("Connector_Generic", "Conn_01x04", JTAG_conn_x, JTAG_conn_y, "JP2", "JTAG")
for n, lbl in (("1", "TMS"), ("2", "TDI"), ("3", "TDO"), ("4", "TCK")):
    place_label_on_pin("JP2", n, lbl, 5)

# # -------------------------------------------------------------
# # 8) Boot-option jumper (IO0 ↔ GND)                             
# # -------------------------------------------------------------
Boot_conn_x, Boot_conn_y = Center_X + 60, Center_Y - 15
add_schematic_symbol("Connector_Generic", "Conn_01x02", Boot_conn_x, Boot_conn_y, "JP4", "BOOT")
place_label_on_pin("JP4", "1", "IO0")
jp4_p2_x, jp4_p2_y = get_pin_location("JP4", "2")  # GND
add_new_wire([jp4_p2_x, jp4_p2_y], [jp4_p2_x, jp4_p2_y-5])  # GND to GND power symbol
add_power_symbol("GND", "#PWR_JP4", jp4_p2_x, jp4_p2_y-5)  # GND power symbol

# # =================  END OF SCHEMATIC =========================