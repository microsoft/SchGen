'''
This module defines configuration settings for the IoTGen project, including paths to Java executables, KiCAD directories, and API keys. It detects the operating system and sets the appropriate paths for Windows, macOS, and Linux environments.

The configurations are based on normal default settings for each OS, but may need to be adjusted based on the user's specific installation paths.
'''

import os
import platform

project_path = os.environ["PROJECT_PATH"]
system = platform.system()

# Replace with your own information
user_name = ""
openrouter_api_key = ""

if system == "Windows":
    JAVA_EXE = "C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.9.10-hotspot\\bin\\java.exe"
    KiCAD_DIR = "C:\\Program Files\\KiCad\\8.0\\share\\kicad"
    freerouting_jar_path = f"C:\\Users\\{user_name}\\Documents\\KiCad\\8.0\\3rdparty\\plugins\\app_freerouting_kicad-plugin\\jar\\freerouting-2.1.0.jar"
    freerouting_plugin_path = f"C:\\Users\\{user_name}\\Documents\\KiCad\\8.0\\3rdparty\\plugins\\app_freerouting_kicad-plugin\\plugin.py"
    KICAD_SYMBOL_LIB_PATH = os.path.join(KiCAD_DIR, "symbols")
    KICAD_FOOTPRINT_LIB_PATH = os.path.join(KiCAD_DIR, "footprints")
    pcbnew_path = "C:\\Program Files\\KiCad\\8.0\\bin\\python.exe"
    python_path = "C:\\Program Files\\KiCad\\8.0\\bin\\python.exe"

elif system == "Darwin":  # macOS
    JAVA_EXE = "/usr/bin/Java"
    KiCAD_DIR = "/Applications/KiCad/KiCad.app/Contents"
    freerouting_jar_path = f"/Users/{user_name}/Documents/KiCad/8.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-2.1.0.jar"
    freerouting_plugin_path = f"/Users/{user_name}/Documents/KiCad/8.0/3rdparty/plugins/app_freerouting_kicad-plugin/plugin.py"
    KICAD_SYMBOL_LIB_PATH = os.path.join(KiCAD_DIR, "SharedSupport", "symbols")
    KICAD_FOOTPRINT_LIB_PATH = os.path.join(KiCAD_DIR, "SharedSupport", "footprints")
    pcbnew_path = os.path.join(KiCAD_DIR, "Frameworks", "Python.framework", "Versions", "Current", "bin", "python3")
    python_path = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"

elif system == "Linux":
    JAVA_EXE = "/usr/bin/java"
    KiCAD_DIR = "/usr/share/kicad"
    freerouting_jar_path = f""
    freerouting_plugin_path = f""
    KICAD_SYMBOL_LIB_PATH = os.path.join(KiCAD_DIR, "symbols")
    KICAD_FOOTPRINT_LIB_PATH = os.path.join(KiCAD_DIR, "footprints")
    pcbnew_path = "/usr/bin/python3"
    python_path = "/usr/bin/python3"
    

else:
    raise RuntimeError(f"Unsupported OS: {system}")


def prepare_context():
    # Load few-shot examples from the files

    example_code_files = [
        "imu_L1.py"
    ]

    # Switch that determine whether to add example code
    add_example_code = 1

    if add_example_code:
        example_codes = []
        for sch_name in example_code_files:
            filename = os.path.join(project_path, "schematic_generation/sch_examples", sch_name)
            if not os.path.exists(filename):
                raise FileNotFoundError(f"Example file {filename} does not exist.")
            with open(filename, "r") as f:
                example_code = f.read()
                example_codes.append(example_code)

        example_code_str = "\n\n".join(example_codes)

    msg_list = [
        {"role": "system",
        "content": f"""
        You need to complete a user request by outputting executable Python code that generates a KiCad schematic file corresponding to the request. Generate the Python code to edit the schematic file using the KiCad Python API. YOU MUST MAKE SURE THE FINAL CODE ALIGN WITH THE THINKING PROCESS.
        ###
        You have the following functions available to you and can create new functions based on them:
        - def add_schematic_symbol(symbol_lib="RF_Module", symbol_name="ESP-WROOM-02", pos_x=150, pos_y=100, reference="U1", value="", rotation=0, mirror:str =None): Add any component symbol from a KiCad library into your schematic. The symbol_lib and symbol_name specify the library and symbol name of the component to add. The pos_x and pos_y specify the position of the center of the symbol in mm. The reference is the unique identifier for the component, e.g., "U1", "R1", "C1". The value is the value of the component, e.g., "10K", "100nF", "ESP32". The rotation is the angle in degrees to rotate the symbol, e.g., 0, 90, 180, 270. The mirror can be "X" or "Y" to flip the symbol according to X or Y axis. If mirror is None, no mirroring is applied.
        NOTE:If there is no related information for value, you need to set a value based on your knowledge about what the schematic design. For example, for a pull up resistor, you can set a value of "10K", for a decoupling capacitor, you can set a value of "100nF". value string should NOT include space or `()` or use `TBD`, for example, `12pF (NC)` should be set as "12pF", and `10K (pull up)` should be set as "10K". 

        - def get_pin_location(symbol_ref: str, pin_name: str): Get the location of a pin in the schematic. Args: symbol_ref (str): The reference of the symbol or label. pin_name (str): The name or id of the pin, for power symbol or label, this should be "1".

        - def add_label(label_pos: list, label_text: str, label_ref: str, label_type: str = "input", text_orient: str ="left"): Add a label to the schematic. The label_pos is a list of two floats [x, y] specifying the position of the label's pin in mm. The label_text is the text of the label, e.g., "IO1", "SDA", "RXD". The label_ref is the unique identifier for the label, e.g., "IO1_0", "SDA_0", "SDA_1". The label_type can be "input", "output", "bidirectional" to specify the type of the label. The text_orient can be "left", "right", "top", or "bottom" to specify the orientation of the text relative to the label pin position.

        """
        + ("""- def connect_pins(sym_a: str, pin_a: str, sym_b: str, pin_b: str). Create a connection between pin_a of symb_a and pin_b of sym_b. The sym_a and sym_b are the references of the symbols or labels to connect. The pin_a and pin_b are the names or ids of the pins to connect. Note: We treat labels as a kind of symbols, identified by their unique reference. For power symbols and labels, they only have one pin, so pin_a or pin_b should be "1".""") + 
        """
        - def write_out_all_wires(). Write out all wires of connections in the schematic.
        """
        + (f"""
        ###
        # # Example code that uses these functions:
        # ```
        # {example_code_str}
        # ```
        ###
        """ if add_example_code else "")
        + f"""
        NOTE:
        1. You should mind the spatial placement of the components. Make sure they are at reasonable positions and ample spacing so that their bounding boxes do not overlap with each other!
        2. The size of the schematic is 210 by 297 mm, size of a A4 paper. It uses a X-Y axes based coordinate system. The origin is [0,0] at bottom left corner of the sheet. X axis is horizontal, and Y axis is vertical. To keep the circuit in the center region. We use the offsets of integers when describing the positions of components, for example, add_schematic_symbol(symbol_lib="power", symbol_name="VAA", pos_x=center_x_1 + (10), pos_y=center_y_1 + (11), reference="#PWR1", value="VIN", rotation=0, mirror="None").
        3. You should check the symbol context to see the spatial information, including the size, orientation, pin locations. The center of the symbol is at (0, 0) and the pin locations are relative to the center of the symbol. X axis is horizontal, and Y axis is vertical. For symbol definition, the Y axis points upward, that means higher Y position means higher position, same direction as the schematic coordinate system.
        4. When using functions of add_schematic_symbol and connect_pins, you MUST be careful about the symbol reference and pin name, you must use the existing reference in the schematic and refer to the symbol context information when determining the pin name.
        5. The code should be valid Python code with correct indentation and syntax. For example, comment should start with #. 
                """}
    ]

    return msg_list