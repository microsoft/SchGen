
import io, sys, traceback, linecache

from contextlib import redirect_stdout
from modules.kicad_sch_interface import *

if __name__ == "__main__":
    import sys
    # open config file to get the project path
    with open("./configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        project_path = lines[0].strip()
        sys.path.append(project_path)


from modules.utils.misc import get_project_path


def run_sch_edit_code(code_string: str, schematic_path: str = None) -> str:
    """
    Execute a piece of Python code that uses KiCad schematic interfaces,
    and return the printed output as a string.
    """

    # If project path is not in the system path, add it
    if get_project_path() not in sys.path:
        sys.path.append(get_project_path())

    if schematic_path is not None:
        target_import = "from modules.kicad_sch_interface import *"
        insert_line = f'set_schematic_filename(r"{schematic_path}")'

        if insert_line not in code_string:
            if target_import not in code_string:
                raise RuntimeError(f"Cannot find import line: {target_import}")

            code_string = code_string.replace(
                target_import,
                f"{target_import}\n{insert_line}",
                1,
            )

    # Create a StringIO buffer to capture the output
    buffer = io.StringIO()
    
    sys.modules.pop("modules.kicad_sch_interface", None) 
    # Provide a restricted global namespace with just 'np'
    # so the code can use `np.array`, `np.sqrt`, etc.
    globals_dict = {
        "__builtins__": __builtins__,
        "__name__": "__main__",
        # "__file__": os.path.join(os.getcwd(), "<string>"),
        }
    
    fake_fname = "sch_editing.py"           # anything unique

    # make the source visible to traceback
    linecache.cache[fake_fname] = (len(code_string),
                                   None,
                                   code_string.splitlines(True),
                                   fake_fname)

    try:
        compiled = compile(code_string, fake_fname, "exec")

        with redirect_stdout(buffer):
            exec(compiled, globals_dict)
        out = buffer.getvalue()
    except Exception:
        out = traceback.format_exc()         # now includes the code line

    return out



if __name__ == "__main__":
    # Example code to run
    code = """
# =============================================================
#  ESP32-S3 minimal functional module – KiCad-Python script
#  (EN label offset enlarged to 15 mm so it clears R1)
# =============================================================
from modules.kicad_sch_interface import *

GRID = 5                 # mm grid step
C_X, C_Y = 150, 100      # ESP32 centre

# -------------------------------------------------------------
# Helper: attach global label outside a pin
# -------------------------------------------------------------
def place_label_on_pin(sym_ref: str, pin_name: str, label: str, extra_dx: int = 0, label_type="bidirectional"):
    x_pin, _ = get_pin_location(sym_ref, pin_name)
    x_sym, _ = get_symbol_location(sym_ref)
    dx = -GRID - abs(extra_dx) if x_pin < x_sym else GRID + abs(extra_dx)
    connect_pin_to_label(sym_ref, pin_name, label, dx, label_type=label_type)

# =============================================================
# 1) ESP32-S3 module & labels
# =============================================================
add_schematic_symbol("RF_Module", "ESP32-S3-WROOM-1", C_X, C_Y, reference="U1", value="ESP32-S3-WROOM-1")
LEFT_IO  = ["EN","IO0","IO1","IO2","IO4","IO5","IO6","IO7","IO8","IO9","IO10","IO11","IO12","IO13","IO14","IO15","IO16"]
RIGHT_IO = ["TXD0","RXD0","IO17","IO18","USB_D-","USB_D+","IO21","IO35","IO36","IO37","IO41","IO45","IO46","IO47","IO48"]
for p in LEFT_IO + RIGHT_IO:
    place_label_on_pin("U1", p, p)
# JTAG aliases
for p, alias in {"IO42":"TMS", "IO40":"TDI", "IO39":"TDO", "IO38":"TCK"}.items():
    place_label_on_pin("U1", p, alias, extra_dx=5)
# Power pins
px, py = get_pin_location("U1", "GND"); add_power_symbol("GND", "#PWR_GND_U1", px, py-GRID); add_new_wire([px, py], [px, py-GRID])
px, py = get_pin_location("U1", "3V3"); add_power_symbol("+3.3V", "#PWR_3V3_U1", px, py+GRID); add_new_wire([px, py], [px, py+GRID])

# =============================================================
# 2) VDD33 rail, decoupling, EN RC
# =============================================================
VDD_X, VDD_Y = 100, 140
add_power_symbol("+3.3V", "#PWR_VDD33", VDD_X, VDD_Y)
add_RLC_symbol("C", 100, 130, "C1", "22uF")
add_RLC_symbol("C", 110, 130, "C3", "100nF")
add_RLC_symbol("R", 120, 130, "R1", "10K", rotation=90)
add_RLC_symbol("C", 120, 120, "C2", "1uF")
# Horizontal bus
add_new_wire([VDD_X, VDD_Y], [130, VDD_Y])
# Drops to parts
for ref in ("C1", "C3", "R1"):
    px, py = get_pin_location(ref, "1"); add_new_wire([px, VDD_Y], [px, py]); add_junction([px, VDD_Y])
# Link C1-1 to C3-1
c1x, c1y = get_pin_location("C1", "1"); c3x, _ = get_pin_location("C3", "1"); add_new_wire([c1x, c1y], [c3x, c1y])
# Grounds
for ref in ("C1", "C3", "C2"):
    gx, gy = get_pin_location(ref, "2"); add_power_symbol("GND", f"#PWR_{ref}", gx, gy-GRID); add_new_wire([gx, gy], [gx, gy-GRID])
# EN node & label (dx = 3·GRID = 15 mm)
r1_2 = get_pin_location("R1", "2"); c2_1 = get_pin_location("C2", "1")
draw_manhattan_wire(r1_2, c2_1, bent_down=True); add_junction(r1_2)
connect_pin_to_label("R1", "2", "EN", 3*GRID)

# =============================================================
# 3) 32 kHz crystal network
# =============================================================
add_schematic_symbol("Device", "Crystal", 110, 80, "X1", "32KHz")
add_RLC_symbol("R", 125, 80, "R2", "70K"); add_RLC_symbol("R", 130, 80, "R3", "12K"); add_RLC_symbol("R", 135, 80, "R5", "12K")
add_RLC_symbol("C", 95, 85, "C4", "12pF"); add_RLC_symbol("C", 95, 75, "C7", "12pF")
io4x, io4y = get_pin_location("U1", "IO4"); add_new_wire([io4x-GRID, io4y], get_pin_location("R2", "1"))
add_new_wire(get_pin_location("R2", "2"), get_pin_location("X1", "1"))
for t in ("C4", "R3"):
    draw_manhattan_wire(get_pin_location("X1", "1"), get_pin_location(t, "1"), bent_down=True)
add_junction(get_pin_location("X1", "1"))
io5x, io5y = get_pin_location("U1", "IO5"); add_new_wire([io5x-GRID, io5y], get_pin_location("R5", "1"))
add_new_wire(get_pin_location("R5", "2"), get_pin_location("X1", "2"))
draw_manhattan_wire(get_pin_location("X1", "2"), get_pin_location("C7", "1"), bent_down=False); add_junction(get_pin_location("X1", "2"))
for ref in ("C4", "C7", "R3", "R5"):
    gx, gy = get_pin_location(ref, "2"); add_power_symbol("GND", f"#PWR_{ref}", gx, gy-GRID); add_new_wire([gx, gy], [gx, gy-GRID])

# =============================================================
# 4) USB-OTG header & filters
# =============================================================
add_schematic_symbol("Connector", "Conn_01x02", 100, 60, "JP3", "USB_OTG")
add_RLC_symbol("R", 120, 60, "R6", "0", rotation=90); add_RLC_symbol("R", 130, 60, "R4", "0", rotation=90)
add_RLC_symbol("C", 120, 50, "C6", "1nF"); add_RLC_symbol("C", 130, 50, "C5", "1nF")
add_new_wire(get_pin_location("JP3", "1"), get_pin_location("R6", "1"))
add_new_wire(get_pin_location("JP3", "2"), get_pin_location("R4", "1"))
connect_pin_to_label("R6", "2", "USB_D-", GRID); connect_pin_to_label("R4", "2", "USB_D+", GRID)
add_new_wire(get_pin_location("R6", "2"), get_pin_location("C6", "1"))
add_new_wire(get_pin_location("R4", "2"), get_pin_location("C5", "1"))
for cap in ("C5", "C6"):
    gx, gy = get_pin_location(cap, "2"); add_power_symbol("GND", f"#PWR_{cap}", gx, gy-GRID); add_new_wire([gx, gy], [gx, gy-GRID])

# =============================================================
# 5) Reset / EN push-button block
# =============================================================
add_schematic_symbol("Switch", "SW_Push", 185, 70, "SW1", "SW_Push")
add_RLC_symbol("R", 195, 70, "R7", "0", rotation=90); add_RLC_symbol("C", 185, 60, "C8", "100nF")
add_new_wire(get_pin_location("SW1", "2"), get_pin_location("R7", "1"))
connect_pin_to_label("R7", "2", "EN", GRID)
add_new_wire(get_pin_location("SW1", "1"), get_pin_location("C8", "1"))
sgx, sgy = get_pin_location("SW1", "1"); add_power_symbol("GND", "#PWR_SW1", sgx, sgy-2*GRID)
add_new_wire(get_pin_location("SW1", "1"), [sgx, sgy-2*GRID]); add_new_wire(get_pin_location("C8", "2"), [sgx, sgy-2*GRID])

# =============================================================
# 6) UART header
# =============================================================
add_schematic_symbol("Connector", "Conn_01x04", 200, 140, "JP1", "UART")
place_label_on_pin("JP1", "2", "RXD0", GRID); place_label_on_pin("JP1", "3", "TXD0", GRID)
px, py = get_pin_location("JP1", "1"); add_power_symbol("+3.3V", "#PWR_JP1_VDD", px, py+GRID); add_new_wire([px, py], [px, py+GRID])
px, py = get_pin_location("JP1", "4"); add_power_symbol("GND", "#PWR_JP1_GND", px, py-GRID); add_new_wire([px, py], [px, py-GRID])

# =============================================================
# 7) JTAG header
# =============================================================
add_schematic_symbol("Connector", "Conn_01x04", 200, 115, "JP2", "JTAG")
for n, lbl in (("1","TMS"),("2","TDI"),("3","TDO"),("4","TCK")):
    place_label_on_pin("JP2", n, lbl, GRID)
add_power_symbol("GND", "#PWR_JP2", 200, 105)

# =============================================================
# 8) Boot-option header
# =============================================================
add_schematic_symbol("Connector", "Conn_01x02", 200, 90, "JP4", "BOOT")
move_symbol("JP4", 0, 0, rotation=180)
place_label_on_pin("JP4", "1", "IO0", ‑GRID)
px, py = get_pin_location("JP4", "2"); add_power_symbol("GND", "#PWR_JP4", px, py-GRID); add_new_wire([px, py], [px, py-GRID])

# ============================ END ===========================
"""

    # code = "from modules.kicad_sch_interface import *\\n\\n# Place resistor R1 (10k) at (150, 100)\\nadd_RLC_symbol(symbol_name=\\\"R\\\", pos_x=150, pos_y=100, reference=\\\"R1\\\", value=\\\"10k\\\")\\n\\n# Place capacitor C1 (0.1uF) at (250, 100)\\nadd_RLC_symbol(symbol_name=\\\"C\\\", pos_x=250, pos_y=100, reference=\\\"C1\\\", value=\\\"0.1uF\\\")\\n\\n# Place a GND power symbol at (350, 100)\\nadd_power_symbol(symbol_name=\\\"GND\\\", reference=\\\"#PWR1\\\", pos_x=350, pos_y=100)\\n\\n# Add a global label for the input net labeled \\\"IN\\\" at (100, 100)\\nadd_global_label([100, 100], \\\"IN\\\")\\n\\n# Connect the net label \\\"IN\\\" to R1 pin 1\\nr1_pin1 = get_pin_location(\\\"R1\\\", \\\"1\\\")\\nadd_new_wire([100, 100], r1_pin1)\\n\\n# Connect R1 pin 2 to C1 pin 1\\nconnect_pins(\\\"R1\\\", \\\"2\\\", \\\"C1\\\", \\\"1\\\")\\n\\n# Connect C1 pin 2 to GND\\nconnect_pins(\\\"C1\\\", \\\"2\\\", \\\"#PWR1\\\", \\\"1\\\")"

#     code = """
# #
# print(test)
# """

    # replace \\\" with \" in the code string
    code = code.replace("\\\"", "\"")
    code = code.replace("\\n", "\n")
    print("Code to be executed:")
    print(code)

    # Run the code and capture the output
    output = run_sch_edit_code(code)
    print("Captured Output:", output)