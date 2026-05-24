# This is to set the path for the module to be imported correctly when running the script directly
if __name__ == "__main__":
    import sys
    # open config file to get the project path
    with open("./configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        project_path = lines[0].strip()
        sys.path.append(project_path)

import os

from modules.sch_module_def import *

from modules.kicad_sch_interface import get_pin_location, load_schematic, save_schematic, save_code, save_description

from modules.utils.kicad_add_symbol import clear_bounding_box_dict

from modules.utils.kicad_scan_lib import *

from modules.utils.kicad_sch_export import get_sch_with_axes

from modules.utils.exec_llm_code import run_sch_edit_code

from modules.utils.llm_interface import GetLLMInterface

from modules.utils.custom_logger import setup_logger

from modules.utils.misc import *

from pydantic import BaseModel

from modules.sch_verifier import SchematicVerifier


def prepare_prompt_context():
    """
    Prepare the prompt context for the LLM.
    This function is used to set up the system message and user request for the LLM.
    """
    
    # Load few-shot examples from the files
    example_code_files = [
        "sch_examples/manual_example_esp32.py",
    ]

    example_codes = []
    for filename in example_code_files:
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Example file {filename} does not exist.")
        with open(filename, "r") as f:
            example_code = f.read()
            example_codes.append(example_code)

    example_code_str = "\n\n".join(example_codes)


    msg_list = [
        {"role": "system",
        "content": f"""
You need to complete carefully about a user request and generate executable Python code to edit a KiCad schematic file according to the request.
First, answer what components you want to add to the schematic, and where you want to place them for correct and easy-to-read wiring and connections.
Second, calculate whether we have enough space for all components and wires to avoid symbol overlap and minimize crossing wires. 
Lastly, generate the Python code to edit the schematic file using the KiCad Python API.
###
You have the following functions available to you and can create new functions based on them:
- add_schematic_symbol(symbol_lib: str = "RF_Module", symbol_name: str = "ESP-WROOM-02", pos_x: float = 150, pos_y: float = 100, reference: str = "U1", value: str = ""): Add any component symbol from a KiCad .kicad_sym library into your schematic.
- add_power_symbol(symbol_name: str = "GND", reference: str = "#PWR1", pos_x: float = 150, pos_y: float = 100): Place a power flag (VCC, GND, etc.) onto the schematic at a given position.

- add_RLC_symbol(symbol_name: str = "R", pos_x: float = 150, pos_y: float = 100, reference: str = "R1", value: str, rotation:int=0): Insert a resistor, inductor, or capacitor symbol from the “Device” lib. If there is no related information for value, you need to set a value based on your knowledge about what the component is far. For example, for a pull up resistor, you can set a value of "10K", for a decoupling capacitor, you can set a value of "100nF". value string should NOT include space or `()` or use `TBD`, for example, `12pF (NC)` should be set as "12pF", and `10K (pull up)` should be set as "10K".

- move_symbol(symbol_ref: str, dx: int, dy: int, rotation: int =0): Move a symbol by dx and dy in mm, and rotate the symbol in degrees (counter-clockwise!). After placing components or power symbols or network labels, you may use this function to adjust the rotation of them to avoid overlap with other components or wires. The rotation is in degrees  (counter-clockwise), and the default is 0 degrees (no rotation). The dx and dy are in mm, and the default is 0 mm (no movement). The symbol_ref is the reference of the symbol, such as "U1", "R1", etc.

- add_junction(junc_pos: list[float]): Drop a net-tie junction dot at the given [x, y] grid position. Each junction marks a connection point for wires. Some cases do not need junctions, like two wire segments meet at a corner, or one wire ends at one pin or one global label. But no penalty for adding junctions at those points, so you can simply add junctions aggressively. But make sure do NOT miss any point where two wires connect, or one wire go through multiple pins or labels. If you are not sure whether to add a junction, you can simply add one at the point.

- add_global_label(label_pos: list[float], label_text: str, label_type: str = "input", text_orient: str = "left"): Place a global net label (-->connect across sheets) at [x, y] with custom text as name. Must be one of "bidirectional", "input", "output", "passive" -- Case sensitive. Should avoid overlap label with components and wires by leaving some space and adding a wire to connect the label. Also, text_orient can be "left", "right", "up", "down" to set the text orientation relative to the label position. The default is "left" which means the text is on the left side of the label position and horizontal along X axis.

- get_global_label_location(label_val: str) -> tuple[float, float]: Return the [x, y] coords of an existing global label by its text.

- add_new_wire(start_pos: list[float], end_pos: list[float]): Draw a horizontal/vertical wire between two points, auto-handling overlaps and junctions. Wire must be horizontal or vertical, can NOT be oblique! if the start or end point is not a pin, you need to add a junction at the start or end point to create the connection.

- draw_manhattan_wire(start_pos: tuple, end_pos: tuple, bent_down: bool = True): Draw a manhattan-style wire using two wire segments between two points in the schematic. Args: start_pos (tuple): The starting position of the wire (x, y). end_pos (tuple): The ending position of the wire (x, y). bent_down (bool): If True, the manhattan wire will be bent down -- chose a corner/junction point with a lower Y value. If False, it will bent upward.

- get_pin_location(symbol_ref: str, pin_ref: str) -> tuple[float, float]: Query the [x, y] location of a symbol’s pin.

- get_symbol_location(symbol_ref: str) -> tuple[float, float]: Query the [x, y] location of a symbol' center position.

- def connect_pin_to_label(symbol_ref: str, pin_name: str, label: str, x_off: float, label_type: str = "bidirectional"): Create and Place a global label and hook it to the given pin. Args: symbol_ref (str): The reference of the symbol. pin_name (str): The name of the pin. label (str): The text of the label. x_off (float): The offset in the x direction from the pin position to the label position. You must specify one of x_off to be non-zero to place the label away from the pin, make sure do not cause overlap between label and component. label_type (str): The type of the label. Must be one of "bidirectional", "input", "output", "passive". The label text will extend along the horizontal direction of wire based on dx, so make sure the label text has enough space to be readable and not overlap with other components or wires. 

###
Coding Rules:
1. The code should be valid Python and should use the KiCad Python API. The code should contain comments, starting with #, to explain what each part does.
2. You should write the code block by block, each block is a piece of code that create a specific block/part of the schematic. For example, for a ESP32 microcontroller module, you should have one main block (including ESP32 symbols and related labels), a power block (including power symbols and related labels), a oscillator block (including crystal and related components and labels), a reset block (including reset button and related components and labels), etc. Each block should be separated by a comment line with the block name. Use labels to connect the blocks together, so that the schematic is easy to read and understand. Do NOT wire everything together with long wires, as that is hard to read. Make sure each block is self-contained with proper labels as interfaces and can be understood independently.
3. To allow enough space between components and symbols, you should use a minimum of 10mm spacing between components, except for power symbols and labels. For example, if you place a component with a pin at (100, 100), the next component should be placed at least at (110, 100) or further away. The power symbols and labels can be placed closer to the components, but still should not overlap with other components or wires.
4. For all pins of the main IC component, like ESP32, ICM20948, you should ONLY connect labels or power symbols with their pins. Other circuitry like decoupling capacitors, pull-up resistors, etc. should be connected to the labels or power symbols at a place away from the main symbol, not directly to the pins. This is to ensure that the schematic is easy to read and understand, and also to avoid confusion with the pin connections. 
5. If json output is asked, Repeat the code again -- copy exactly, in the json output. Do NOT say something like "[see Python listing above]"!
###
# Example code that uses these functions:
```
{example_code_str}
```
###
NOTE:
1. You should mind the spatial placement of the components. Make sure they are at reasonable positions and ample spacing so that they do not overlap with each other! The wires should also not overlap with the components. You can simply the wiring with correct placement or use multiple network or power labels. The wire segments should be horizontal or vertical, and can not be oblique. If you are not sure whether connect_pin() may cause overlap, you can use add_new_wire() to draw the wires between two points. If two points are not along the same axis, you need to create two wires along each axis to draw a manhattan-style wire.
2. The size of the schematic is 233 by 165. We use grids to put all symbols, which is 1.27 by 1.27 mm., So you should make sure all the coordinates are integers and align them with the symbolsize in mm.. It uses a X-Y axes based coordinate system. The origin is [0,0] at bottom left corner of the sheet. X axis is horizontal, and Y axis is vertical. To keep the circuit in the center region, You should use X coordinate in the range of [75, 225], Y coordinate in the range of [50, 150].
3. You should check the symbol context to see the spatial information, including the size, orientation, pin locations. You can use the function `move_symbol` to move or rotate the symbol placement. The local coordinates for symbol body and pin locations are in mm. The center of the symbol is at (0, 0) and the pin locations are relative to the center of the symbol. X axis is horizontal, and Y axis is vertical. For symbol definition, the Y axis points upward, that means higher Y position means higher position, same direction as the schematic coordinate system.
4. The code should be valid Python code with correct indentation and syntax. For example, comment should start with #. 
5. You can use global label to mark Output and Input if the use is asking for simple analog circuit. For example, use "Vout" for output and "Vin" for input. Make sure the labels are correctly placed and connected to circuit, either by connecting to a pin or connecting to a wire by adding a wire and junction. Note that by default, the global label text is at the left side of pin and the label is horizontal along X axis. You can use the function `get_global_label_location` to get the location of the global label.
6. For any position that have 2 wires connected, you must add a junction at the position, unless it is a corner where two wire segment ends meet. Make sure do Not miss any point. You can use the function `add_junction` to add a junction at the given [x, y] grid position. For example, for a GND pin, when you connect it with two wires at its pin location, you need to add a junction at the pin location. For two wires, if they intersect at a point, if want them to be connected, you need to add a junction at the intersection point.
7. You should utilize the information in the symbol content to help with schematic editing. For example, you can not use pin names not present in the symbol content. Based on the sizes mentioned in the context, you should avoid overlapping components and wires. You should also use the pin locations to place related components at suitable locations and connect the pins correctly.
8. It is correct and encouraged to use multiple same valued net/global label or power symbols to simplify the schematic design. If there is a reference design, follow it in terms of using global labels. Do NOT replace a label with long wire as that is hard to read. For example, if there are multiple GND pins, you can use multiple GND symbols to connect them together, so that no long wires are needed. Net labels are used to simplify schematic internal to current module, while global labels are used to connect across different modules or sheets. For microcontroller like ESP32, MSP430, they have many pins like GPIOs, TX, RX, you should add global labels for all of them so that other modules can connect to them easily. For example, you can add a global label for the IO11 pin of ESP32, so that other modules can connect to it easily.
9. When using connect_pin_to_label(), you do not need to create a global label as it will automatically be created for you. Also, make sure the offset is chosen correctly to avoid overlap. The offset should be along the direction of the pin you want to connect. For example, the EN and BOOT pins for ESP32 may be on the left side of the rectangular symbol and pin extend towards left side, so you should use x_offset < 0 and y_offset = 0 so that the wire and label text extends towards the right direction, instead of overlapping with the symbol. Do NOT use y_offset if the pin is along horizontal direction, which causes overlap! For example, `connect_pin_to_label("JP4", "2", "IO0", 0, 10)\nconnect_pin_to_label("JP4", "1", "GND",  0, -10)` causes overlap because the JP4 pin 2 is lower than pin 1, while the offset is 10mm up for pin 2, making the wire overlap with JP4 pin 1. Since JP connecters have their pins in the horizontal direction by default, you should use `connect_pin_to_label("JP4", "2", "IO0", 10, 0)\nconnect_pin_to_label("JP4", "1", "GND", 10, 0)` to extend wire along X axis and avoid overlap.
10. If a reference image is available, The pin names for the same component can be different in reference image versus in KiCAD. You should follow the meaning of reference schematic, but use the pin names in the KiCAD symbol context. For example, the ESP32 S1 WROOM in the reference schematic has IO19, but IO19 is named as USB_D+ in kiCAD symbol. 
        """}
    ]

## For original kicad coordinate system
# 2. The size of the schematic is 233 by 165 mm. It uses a X-Y axes based coordinate system. The origin is [0,0] at upper left corner of the sheet. X axis is horizontal, and Y axis is vertical. Not that the position is lower when Y axis is larger. To keep the circuit in the center region, You should use X coordinate in the range of [75, 225], Y coordinate in the range of [50, 150]. The unit is in mm. 

    return msg_list



class SchematicEditor:
    """
    This class is used to edit a KiCad schematic file using Python code generated by LLM.
    It takes user request and uses the KiCad Python interface to perform the editing tasks.
    """

    def __init__(self, model:str = "o3", schematci_path:str = None, save_path: str = "./schematic_dataset", schematic_name: str = "schematic"):
        
        # O4 is better at visual tasks, O3 is better at complex reasoning tasks
        self.llm_o4 = GetLLMInterface(model_name="o4-mini", model_provider="Azure")
        self.llm_o3 = GetLLMInterface(model_name="o3", model_provider="Azure")
        
        if model == "o4":
            self.llm = self.llm_o4
        elif model == "o3":
            self.llm = self.llm_o3

        self.logger = setup_logger()
        self.logger.info("SchematicEditor initialized.")

        if schematci_path is not None:
            self.schematic_path = schematci_path
            # Set the project path to the schematic path
            set_schematic_path(schematci_path)
        else:
            self.schematic_path = get_schematic_path()

        # local msg cache
        self.msg_list = None
        # self.msg = prepare_prompt_context()

        self.verifier = SchematicVerifier(o3_flag=False) # Azure O3 currently not available, so use O4-mini for verification
        self.save_path = os.path.join(save_path, schematic_name)
        os.makedirs(self.save_path, exist_ok=True)

    def cache_initial_sch(self):
        """
        Cache the initial schematic file.
        This function is used to save the initial state of the schematic file before any editing.
        """
        self.logger.info("Caching initial schematic...")
        self.logger.debug(f"Schematic path: {self.schematic_path}")

        with open(self.schematic_path, "r") as f:
            # save all content to a variable
            self.initial_schematic = f.read()
        self.logger.info("Initial schematic cached.")
    
    def restore_initial_sch(self):
        """
        Restore the initial schematic file.
        This function is used to restore the initial state of the schematic file after editing.
        """
        self.logger.info("Restoring initial schematic...")
        self.logger.debug(f"Schematic path: {self.schematic_path}")

        with open(self.schematic_path, "w") as f:
            # write the initial schematic content back to the file
            f.write(self.initial_schematic)
        self.logger.info("Initial schematic restored.")

    def describe_sch_image(self, prompt, img_path: str):
        """
        Describe the schematic image using LLM.
        This function is used to describe the schematic image to the LLM so that it can understand the schematic better, especially the spatial relations and wire connections.
        """

        assert os.path.exists(img_path), f"Image path {img_path} does not exist."

        self.logger.info("Describing reference schematic image...")
        

        # Then, describe the NETS AND WIRING. List all the nets similar to a netlist file. For each net, you need to describe how and where it is connected, either through labels or wiring connections. Explicitly list all labels used in the schematic, including global labels and local labels. Explicitly list all wiring connections, including the start and end points of the wire, and the orientation of the wire segments.

        # 1. Describe the schematic image
        
        # prepare the message for LLM
        local_msg = self.llm.prepare_input_with_image(prompt, img_path)

        # 2. Get the response from LLM
        response = self.llm.get_string_response(local_msg)

        self.logger.info("Schematic image described.")
        self.logger.info(f"Response: {response}")

        return response



    
    def execute_code(self, code: str):
        """
        Execute the generated code.
        This function is used to execute the Python code generated by LLM to edit the schematic file.

        Args:
            code (str): The Python code to be executed.
        Returns:
            str: The error output of the executed code, or None if successful.
        """
        self.logger.info("Executing code...")
        self.logger.debug(f"Code: {code}")

        # replace \\\" with \"
        code = code.replace("\\\"", "\"")
        code = code.replace("\\n", "\n")

        # 3. Run the generated code
        output = run_sch_edit_code(code)
        self.logger.info("Code executed.")
        self.logger.info(f"Output: {output}")
        self.logger.info("Schematic drawing finished.")

        if "error" in output.lower():
            self.logger.error(f"Error in executing code: {output}")
            return output
        else:
            return None

    
    def load_related_symbols(self):
        """
        Load related symbols from the library.
        This function is used to load the symbols from the library that are related to the user request.
        """
        self.logger.info("Loading related symbols...")

        # pass
        # TODO: Implement this function to load related symbols from the library
        
        # 0. Load the library information
        sym_lib_dict = load_organized_lib("./export/organized_lib.json")
        self.sym_lib_dict = sym_lib_dict
        self.logger.info("Organized lib info loaded.")

        # NOTE: Can NOT find the symbols in one go due to limited context length of LLM

        ref_img_require = "Make sure include librates and symbols that are used in the reference image provided below. "
        # 1. find related libraries
        find_lib_question = f"""
Find the related schematic libraries for the following user request for a circuit schematic: {self.sch_request}
{ref_img_require if self.img_ref_path is not None else ""}
###
We have the following libraries as listed below:
{list(sym_lib_dict.keys())}
### 
NOTE: 
0. You must use the library name exactly as listed above, without quotes, and the library name is case sensitive.
1. Always include the "Device" library in the list of libraries because it contains the basic components such as resistors, capacitors, and inductors.
2. Always include the "power" library in the list of libraries because it contains the power symbols such as VCC and GND.
3. The libraries are organized by their function and usage. For example, the "RF_Module" library contains RF modules, while the "Device" library contains basic components.
4. Include all related libraries that are relevant to the user request, even if they may not be actually used in the final design.
5. ESP32 related modules are in the "RF_Module" library, so you should include RF_Module if the user request is related to ESP32. 
6. Other frequently used libraries you should include are "Sensor", "Connector".
        """


        # If there is an image reference, include it in the message and ask LLM to replicate the schematic in the image
        if self.img_ref_path is not None:
            local_msg = self.llm.prepare_input_with_image(find_lib_question, self.img_ref_path)
        else:
            local_msg = [{
                "role": "user",
                "content": find_lib_question,
            }]


        response, data_obj = self.llm.get_json_response_retry(
                                local_msg, 
                                RelatedLibs
                                )
        self.logger.info(f"Response: {response}")
        self.logger.info(f"Related libs object: {data_obj}")


        # 2. load related symbols from the libraries
        filtered_libs = data_obj.libs
        filtered_lib_info = {}
        for lib_name in filtered_libs:
            assert lib_name in sym_lib_dict, f"Library {lib_name} not found in the organized library."

            minimal_sym_info = []
            for sym_info in sym_lib_dict[lib_name]:
                tmp_info = sym_info.copy()
                tmp_info['symbol'] = "" # remove the symbol info
                tmp_info['datasheet'] = "" # remove the datasheet info
                tmp_info["footprint"] = "" # remove the footprint info
                minimal_sym_info.append(tmp_info)

            filtered_lib_info[lib_name] = minimal_sym_info
        self.logger.info("Filtered lib info Done.")

        # 2.1 Find the symbols related to the user request

        symbol_list = []

        TRUNCATE_LEN = 500e3
        # If lib info is too long, truncate it and ask LLM multiple times
        ask_times = int(len(str(filtered_lib_info)) // TRUNCATE_LEN + 1)

        lib_ct = 0
        for i in range(ask_times):
            
            tmp_lib_info = {}
            for j in range(lib_ct, len(filtered_libs), 1):
                # tmp_lib_info[filtered_libs[j]] = filtered_lib_info[filtered_libs[j]]
                # if len(str(tmp_lib_info)) > TRUNCATE_LEN:
                #     lib_ct = j
                #     break
                if len(str(tmp_lib_info)) + len(str(filtered_lib_info[filtered_libs[j]])) > TRUNCATE_LEN:
                    break
                else:
                    tmp_lib_info[filtered_libs[j]] = filtered_lib_info[filtered_libs[j]]
                    lib_ct = j+1

            # formatted_lib_info = "\n".join([(f"{sym_info['name']}: {lib_name}, description: {sym_info['description']}" for sym_info in sym_list) for lib_name, sym_list in tmp_lib_info.items()])
            formatted_lib_info = ""
            for lib_name, sym_list in tmp_lib_info.items():
                for sym_info in sym_list:
                    formatted_lib_info += f"Name: {sym_info['name']}, Library: {lib_name}, description: {sym_info['description']}\n"

            self.logger.info(f"Asking LLM for related symbols ({i+1} / {ask_times})")
            find_symbol_question = f"""
Find the related schematic symbols for the following user request for a circuit schematic: {self.sch_request}
{ref_img_require if self.img_ref_path is not None else ""}
###
We have the following Symbols in different libraries as listed below:
{formatted_lib_info}
###
NOTE:
1. You should include all related symbols, even for simple components like resistors, capacitors, and inductors, power symbols.
"""

            if self.img_ref_path is not None:
                local_msg = self.llm.prepare_input_with_image(find_symbol_question, self.img_ref_path)
            else:
                local_msg = [{
                    "role": "user",
                    "content": find_symbol_question,
                }]

            response, data_obj = self.llm.get_json_response_retry(
                                    local_msg, 
                                    RelatedSymbols
                                    )
            self.logger.info(f"Response: {response}")
            self.logger.info(f"Related symbols object: {data_obj}")
            
            symbol_list += data_obj.symbols
        


        # 3. return the symbols

        symbol_info_list = []
        for sym in symbol_list:
            assert sym.lib_name in self.sym_lib_dict.keys(), f"Library {sym.lib_name} not found in the organized library."

            # Search over the symbol lib info to find the full length symbol info
            for item in self.sym_lib_dict[sym.lib_name]:
                if item['name'] == sym.name or item['name'] == f'"{sym.name}"':

                    # if extends, copy symbol info from the source symbol
                    if "extends" in item:
                        self.logger.debug(f"Symbol {sym.name} extends another symbol: {item['extends']}.")
                        for tmp_item in self.sym_lib_dict[sym.lib_name]:
                            if tmp_item['name'] == item["extends"]:
                                if 'symbol' in tmp_item:
                                    item['symbol'] = tmp_item['symbol'].copy()
                                    # replace symbol name to the current one
                                    for sym_def in item['symbol']:
                                        sym_def[1] = sym_def[1].replace(tmp_item['name'].replace('"', ''), item['name'].replace('"', ''))
                                break
                    
                    # append the symbol info to the list
                    symbol_info_list.append(item)
                
        return symbol_list, symbol_info_list


    def describe_symbol_info(self, symbol_list: list, symbol_list_info: list):
        """
        Describe the symbols and related context information (spatial size, pin names and locations, etc.)
        This function is used to describe the symbols and their related context information.
        """
        self.logger.info("Describing symbol info...")

        describe_symbol_question = f"""
Describe all the symbols below and their related context information: which library, spatial information like shapes, sizes, pin names and locations etc.
###
We have the following symbols as listed below:
{symbol_list}
They have the following context information:
{symbol_list_info}
###
NOTE: 
1. The coordinate system for the symbol is by X and Y axes, with the origin at the center of the symbol. The X axis is horizontal, and the Y axis is vertical. The Y axis points upward, that means higher Y position means higher position. The X axis points to the right, that means higher X position means right side position.
2. If there are many pins, besides the numeric locations, you also need to verbally describe the pin locations, such as "upper", "lower", "left", "right", "upper right, 4th from top to down" etc. 
3. Make sure list the exact pin names or numbers, such as "1" for R L C components, "Pin 1" for connectors, "EN", "IO1" for microcontroller pins, etc. The pin names are case sensitive.
4. The pin orientation is decided by the relative position from the main symbol body to the pin location, for example, pin on the left side of the symbol should list as point towards left. Do NOT say things like "Pins (passive, left side, pointing right;", which is wrong. Ignore KiCAD's pin orientation information, which is reversed to our purpose.
### Example description for a resistor symbol:
1) Symbol “R” (Resistor)
 • Library: "Device"
 • Description: generic two-terminal resistor
 • Graphic: simple rectangle
   - Rectangle corner1 at (-1.016, -2.54), corner2 at (+1.016, +2.54)
   - Rectangle stroke width 0.254 mm, no fill
 • Bounding box of the resistor body:
   - Width = 2.032 mm (from x=-1.016 to +1.016)
   - Height = 5.08 mm (from y=-2.54 to +2.54)
 • Pins (both passive):
   Pin 1
     - Number: “1”
     - Name: “~” (parameter-driven)
     - Attachment point at (0, +3.81), *upper* of the rectangle symbol body
     - Orientation: pin location is above the rectangle body, pointing Upward
     - Length: 1.27 mm (so the pin segment runs from y=+3.81 down to y=+2.54, exactly meeting the rectangle)
     - Label font size: 1.27 x 1.27 mm
   Pin 2
     - Number: “2”
     - Name: “~”
     - Attachment point at (0, -3.81), *lower* of the rectangle symbol body
     - Orientation: pin is below the rectangle body, pointing downward
     - Length: 1.27 mm (from y=-3.81 up to y=-2.54)
     - Label font size: 1.27 x 1.27 mm
3) Symbol “ESP32-S3-WROOM-1” (RF/Microcontroller module)
 • Library: "RF_Module"
 • Description: Espressif ESP32-S3-WROOM-1 Wi-Fi/BLE RF module with onboard antenna
 • Graphic:
   - Main rectangle from (–12.7, +25.4) to (+12.7, –25.4)
     • Width = 25.4 mm, Height = 50.8 mm
     • Stroke = 0.254 mm, filled background
   - Label “PSRAM” at (x=+5.08, y=+2.54), rotated 90° (text orientation), font 1.27×1.27 mm
   - Small rectangle (outline) marking PSRAM area:
     from (x=+6.35, y=–1.27) up to (x=+7.62, y=+6.35)
 • Pins (all length 2.54 mm, font 1.27×1.27 mm):
   – Bottom side of the symbol body (y≈–27.94), pointing downward:
     • Pin 1: GND, power_in, at (0, –27.94)
     • Pin 40, 41: GND, passive, both hidden, at same (0, –27.94), orient=90°
   – Top side of the symbol body, pointing upward:
     • Pin 2:  3V3, power_in,    at (0, +27.94)
   – Right side (x≈+15.24) of the symbol body, pointing right, pins from top to bottom:
     • Pin 37: TXD0 at y=+22.86  
     • Pin 36: RXD0 at y=+20.32  
     • Pin 10: IO17 at y=+17.78  
     • Pin 11: IO18 at y=+15.24  
     • Pin 13: USB_D– at y=+12.70 (alternate IO19)  
     • Pin 14: USB_D+ at y=+10.16 (alternate IO20)  
     • Pin 23: IO21 at y= +7.62  
     • Pin 28: IO35 at y= +5.08  
     • Pin 29: IO36 at y= +2.54  
     • Pin 30: IO37 at y=  0.00  
     • Pin 31: IO38 at y=–2.54  
     • Pin 32: IO39 at y=–5.08  
     • Pin 33: IO40 at y=–7.62  
     • Pin 34: IO41 at y=–10.16  
     • Pin 35: IO42 at y=–12.70  
     • Pin 26: IO45 at y=–15.24  
     • Pin 24: IO47 at y=–20.32  
     • Pin 25: IO48 at y=–22.86  
     • Pin 16: IO46  at (x=+15.24, y=–17.78) belongs on right side
   – Left side (x≈–15.24) of the symbol body, pointing towards left, pins from top to bottom:
     • Pin 3:  EN,   at y=+22.86
     • Pin 27: IO0   at y=+17.78  
     • Pin 39: IO1   at y=+15.24  
     • Pin 38: IO2   at y=+12.70  
     • Pin 4:  IO4   at y= +7.62  
     • Pin 5:  IO5   at y= +5.08  
     • Pin 6:  IO6   at y= +2.54  
     • Pin 7:  IO7   at y=  0.00  
     • Pin 12: IO8   at y=–2.54  
     • Pin 17: IO9   at y=–5.08  
     • Pin 18: IO10  at y=–7.62  
     • Pin 19: IO11  at y=–10.16  
     • Pin 20: IO12  at y=–12.70  
     • Pin 21: IO13  at y=–15.24  
     • Pin 22: IO14  at y=–17.78  
 • Each pin label and number drawn in 1.27×1.27 mm font
"""
        # TODO: What's the format for the symbol shapes descriptions?
        
        msg_dict = {
            "system": "",
            "user": describe_symbol_question,
        }
        response = self.llm.get_string_response(
                                self.llm.dict_to_msg(msg_dict)
                                )
        
        self.logger.info(f"Response: {response}")

        return response



    def prepare_symbol_context(self):
        """
        Select and Edit the placement of components in the schematic.
        This function is used to edit the placement of components in the schematic file.
        """
        self.logger.info("Editing placement...")

    
        # 1. Load related symbols from the library
        # 2. Select related symbols from the library
        symbol_list, symbol_list_info = self.load_related_symbols()


        # 3. Describe symbols and related context information (spatial size, pin names and locations, etc.)
        symbol_context = self.describe_symbol_info(symbol_list, symbol_list_info)

        return symbol_context



    def edit_sch_with_visual_feedback(self):
        """
        Edit the connections of components in the schematic.
        """

        # TODO: Use the symbol context to generate the code for schematic editing

        # Iteratively edit the schematic with visual feedback from LLM
        max_iter = 50
        feedback_info = None
        current_sch_img = None

        cached_clear_sch = load_schematic(get_schematic_path())
        cached_correct_sch = None

        for i in range(max_iter):
            
            self.logger.info(f"Editing schematic, iteration {i+1}/{max_iter}...")

            # 0. Clear up the current schematic file
            self.logger.debug("Clearing up the current schematic file...")
            save_schematic(cached_clear_sch, get_schematic_path())
            self.logger.debug("Clearing up the bounding box dictionary...")
            clear_bounding_box_dict()


            # 1. Generate the code using LLM

            if i > 0:
                local_request = f"""
Check the following feedback for the schematic and improve your schematic editing code. Make sure provide the complete python code, not just the updates!
First answer why the errors happened, and then how we can move the symbol and label placement to make the task easier, then how to fix the wiring connections.
###
""" + \
                "Feedback: \n" + (feedback_info if feedback_info else "") + \
                "\n\nHere is the current schematic image: " 
                # self.msg_list.append({"role": "user", "content": local_request})
                image_msg = self.llm.prepare_input_with_image(local_request, current_sch_img)
                assert isinstance(image_msg, list) and len(image_msg) == 1, "Image message should be a list."
                self.msg_list.append(image_msg[0])


            while True:
                self.logger.debug("Calling LLM to generate code...")
                try:
                    response, code_obj = self.llm.get_json_response_retry(self.msg_list, SchematicEditCode)
                    break
                except Exception as e:
                    self.logger.error(f"Error: {e}")
                    self.logger.info("Retrying to get response...")
            

            self.msg_list.append({"role": "assistant", "content": response})

            self.logger.info(f"Response: {response}")


            # 2. Run the generated code
            exec_err = self.execute_code(code_obj.code)
            current_sch_img = get_sch_with_axes()
            self.logger.debug(f"Got current schematic image: {current_sch_img}")

            if exec_err is not None:
                feedback_info = f"Error in executing code: {exec_err}\nPlease fix the code and try again."
                continue

            # 3. Provide visual feedback to LLM
            response, feedback_obj = self.get_visual_feedback()

            veri_response, veri_feedback_obj = self.verifier.netlist_verify(self.sch_request, self.img_ref_path)

            response += "\n######\nNetlist Verification Feedback:\n" + veri_response

            feedback_score = feedback_obj.score + veri_feedback_obj.score

            if feedback_score < 0:
                self.logger.info("Feedback: Schematic design has errors, need to fix it.")
                feedback_info = response
            elif feedback_score == 0:
                cached_correct_sch = load_schematic(get_schematic_path())
                self.logger.info("Feedback: Schematic design is correct but can be improved.")
                feedback_info = response
            elif feedback_score > 0:
                self.logger.info("Feedback: Schematic design is correct and well-designed.")
                cached_correct_sch = load_schematic(get_schematic_path())
                break

        # 4. Save the final schematic file
        if cached_correct_sch is not None:
            self.logger.info("Saving the final schematic file...")
            save_schematic(cached_correct_sch, get_schematic_path())
            # The code is saved to save_path/{self.schematic_name}/code.py
            code_path = os.path.join(self.save_path, "code.py")
            save_code(code_obj.code, code_path)
            self.logger.info("Final schematic file saved.")


    def get_visual_feedback(self):
        """
        Get visual feedback from LLM to guide further editing.
        """
        self.logger.info("Providing visual feedback...")


        # 1. extract the schematic image.
        sch_img_path = get_sch_with_axes()
        self.logger.info(f"Schematic image extracted. {sch_img_path}")

        # 2. Use LLM to provide feedback on the schematic image.
        sch_vision_question = f"""
Check the kicad schematic image generated by the code above and provide feedback on the schematic image.
There are two levels of feedback: warnings and errors.
Error include electrical connection errors like short circuit, open circuit, circuit component overlay, or the current design conflicts with or fail to follow the user request.
Warning include design issues like misaligned component placement, unreadable wire connections, that can be improved to create a better schematic design but not errors. 
###
Output format:
1. First, provide a score from -1, 0, or 1, where -1 means the schematic is not correct, 0 means the schematic is correct but can be improved, and 1 means the schematic is correct and well-designed.
2. Then, provide a list of errors and warnings. Go through the following types of errors:
(1) symbol_overlaps: where you can find component and symbols overlap with each other, such as a GND or power symbol inside the rectangle of another symbol.
(2) wire_overlaps: where you can find wires overlap with each other, such as a wire going through a component symbol or a wire going through another wire.
(3) missed_connections: where you can find missed connections, such as a wire not connected to a pin or label.
3. Finally, provide suggestions to fix the errors and warnings. Be specific about the suggested operations, such as the specific numbers of positions, orientation moves.
###
Important NOTE:
1. Focus on the image. Think carefully about the schematic, do not provide feedback unless you are sure about the issues.
2. The dashed lines in the image is for reading the coordinates only. Dashed lines are not part of the schematic and should not be considered as wires.
3. It is correct and encouraged to use multiple same valued net/global label or power symbols to simplify the schematic design. For example, if there are multiple GND pins, you can use multiple GND symbols to connect them together, so that no long wires are needed.
4. Common errors include: (1) Components or symbols overlap with each other. For example, placing a GND or power symbol inside the rectangle of another symbol is an error. Adjust the component placement and wiring to correct the schematic. (2) Global labels are placed above the pin, and the wire between the pin and label crosses other pins, causing overlap and unwanted connections! This is an severe error and should be corrected by adjusting the label and wire positions.
5. Some common issues are: (1) placing the components too close to each other. (2) wire goes through the component and create overlay. A wire goes through a component symbol is a warning, you should suggest a different wiring path to avoid the wire going through the component symbol.
"""        
        # self.msg_list.append({"role": "user", "content": sch_vision_question})

        image_msg = self.llm.prepare_input_with_image(sch_vision_question, sch_img_path)
        assert isinstance(image_msg, list) and len(image_msg) == 1, "Image message should be a list."
        self.msg_list.append(image_msg[0])

        # 3. return the feedback from LLM
        # response = self.llm.get_string_response(self.msg_list)
        response, feedback_obj = self.llm.get_json_response_retry(self.msg_list, VisionFeedbackDef)
        self.logger.info(f"Schematic visual feedback Response: {response}")

        return response, feedback_obj


    def draw_schematic(self, sch_request: str, img_ref_path: str = None):
        """
        Draw a schematic based on user request.
        This function generates Python code using LLM and executes it to edit the schematic file.

        Args:
            sch_request (str): The user request for the schematic.
            img_ref_path (str): Optional path to an image reference for the desired schematic.
        """
        self.logger.info("Starting to draw schematic...")
        self.logger.debug(f"User request: {sch_request}")

        # 1. Prepare the prompt context
        self.sch_request = sch_request
        self.img_ref_path = img_ref_path
        self.msg_list = prepare_prompt_context()

        describe_question = f"""
    Check the circuit schematic image carefully, describe it in details, especially the spatial relations.
    First, list components in the schematic, including their reference, value, position, orientation. The components labeled with `NC` means `no component/connect`, which means they are optional components that can be omitted. 
    Then, describe the connections between components, including the wires and junctions.
    Make sure you think carefully about how the wires are connected, some connections have junctions, some connections are just two wires meet at a corner, some connections are wires connected to pins or labels.
    ### 
    NOTE:
    1. To describe the position, you need first select reference points, such as the most central or important component or one of the pins of the central component. To handle different scale, use resistor or capacitor or text labels as a size reference, resistor or capacitor is 8mm from one pin to the other end, text is typically 4mm in height. Then you can describe the position of other components relative to the reference point. For example, "The resistor R1 is located 50mm to the right of the ESP32 U1 pin IO1, and 20mm below it." or "The capacitor C1 is located 30mm to the left of the power symbol #PWR1." Make sure that the minimal unit for position is 10mm or 5mm to allow reasonable spacing.
    2.  To describe wiring connection, you must describe the start and end points of the connection with pin specified, e.g., from component A pin 1 to component B pin 2. If the wire connection has multiple segments, you need to describe their orientation for each of them. For example, "ESP32 pin 1 is connected to resistor R1. the wire goes 20mm to the right, then 10mm down, and finally connects to pin 1 of R1." or "The wire from the power symbol #PWR1 goes 30mm to the left, then 10mm down, and finally connects to pin 2 of C1."
    3. To describe the component orientation, you need to describe whether the component is horizontal or vertical, and how the pins are oriented. For example, "The resistor R1 is horizontal, with pin 1 on the left side and pin 2 on the right side." or "The capacitor C1 is vertical, with pin 1 on the top side and pin 2 on the bottom side."
    (Hint: For some components, the pin is not named with a number, for example, diode, the pin is named with a symbol like "K" or "A". You should describe the pin name, its location and connections.)
    """
        self.img_ref_description = self.describe_sch_image(prompt=describe_question, img_path=self.img_ref_path) if self.img_ref_path is not None else None

        summarize_question = f"Check the circuit schematic image carefully, summarize its functions, including the characteristics of the module, input/output, and how it works as a part of the system."
        # Save the image reference description
        if self.img_ref_description is not None:
            description_path = os.path.join(self.save_path, "detailed_description.txt")
            save_description(self.img_ref_description, description_path)
            self.logger.info("Prompt context prepared.")
        
        if summarize_question is not None:
            self.logger.info("Summarizing the schematic image...")
            summary = self.describe_sch_image(prompt=summarize_question, img_path=self.img_ref_path)
            summary_path = os.path.join(self.save_path, "concise_description.txt")
            save_description(summary, summary_path)
            self.logger.info("Schematic image summarized.")

        # 2. Bootstrap the initial schematic file, Focusing on gathering symbols and related context information
        self.logger.info("Gathering symbols and related context information...")

        # If there is a cached symbol context, load it
        CONTEXT_CACHE_PATH = "./export/cached_symbol_context.json"
        symbol_context = None
        if os.path.exists(CONTEXT_CACHE_PATH):
            self.logger.info("Loading cached symbol context...")
            with open(CONTEXT_CACHE_PATH, "r", encoding='utf-8') as f:
                cached_data = json.load(f)
                if self.sch_request == cached_data["user_request"]:
                    symbol_context = cached_data["symbol_context"]
                    self.logger.info("Cached symbol context loaded.")
                else:
                    self.logger.info("Cached symbol context does not match the user request, preparing new symbol context...")
        else:
            self.logger.info("No cached symbol context found, preparing new symbol context...")

        if symbol_context is None:
            # Prepare the symbol context 
            symbol_context = self.prepare_symbol_context()

            # Save the cached symbol context and user request a json file
            with open(CONTEXT_CACHE_PATH, "w", encoding='utf-8') as f:
                json.dump({
                    "user_request": self.sch_request,
                    "symbol_context": symbol_context,
                }, f, indent=4, ensure_ascii=False)

        # 3. Generate code for schematic editing, including placement and connections
        self.logger.info("Generating code for schematic editing...")

        if self.img_ref_path is None:
            self.msg_list.append({"role": "user", 
                                "content": f"""
    The user request is: {self.sch_request}
    ###
    We have the following symbols and their related context information as listed below:
    {symbol_context}
    ###
    """
                                })
        else:
            # If there is an image reference, include it in the message and ask LLM to replicate the schematic in the image
            self.msg_list += self.llm.prepare_input_with_image(
    f"""
    The user request is: {self.sch_request}
    You need to check the image carefully and replicate the schematic in the image.
    ###
    We have the following symbols and their related context information as listed below:
    {symbol_context}
    ###
    """ + \
    f"You should follow the image reference for the symbols and netlist connections, while the placement and wiring can be different. The image reference has the following description: {self.img_ref_description}" if self.img_ref_description else "",
    self.img_ref_path
            )

    
        self.edit_sch_with_visual_feedback()







class SchematicEditCode(BaseModel):
    explanation: str
    code: str


if __name__ == "__main__":

    # user_request = "Draw a schematic of a simple RC circuit with a resistor and capacitor in series."

    # user_request = "Draw a schematic of a voltage divider circuit with two resistors and a capacitor that connects to ground for filtering."
    # img_ref_path = "./testing_kicad_proj/voltage_divider.png"

    # user_request = "Draw a schematic of a minimal functional module for ESP32 according to the provided image. "
    # # img_ref_path = None  # "./testing_kicad_proj/esp32_wroom_32e.png"
    # img_ref_path = "./testing_kicad_proj/esp32-wroom.png"


    # user_request = "Draw a connector that has 4 pins and connections to components as shown in the image. "
    # img_ref_path = "./testing_kicad_proj/connector1x4.png"


    # user_request = "Draw the schematic for this ICM20948 module using I2C. "
    # img_ref_path = "./testing_kicad_proj/ICM20948.png"

    # user_request = "Draw the schematic for this BME280 module with I2C connections. "
    # img_ref_path = "./testing_kicad_proj/BME280.png"

    module_name = "power_led"
    user_request = "According to the image provided, draw the schematic of the power LED."
    img_ref_path = "./testing_kicad_proj/{}.png".format(module_name)

    sch_editor = SchematicEditor(model='o4', schematic_name=module_name)

    sch_editor.draw_schematic(user_request, img_ref_path)

#     sch_editor.execute_code("""
# #  Power ‑LED branch   ( 3.3 V → TP1 → R4 → LED → GND )
# # -------------------------------------------------------------
# from modules.kicad_sch_interface import *
# # -------------------------------------------------------------
# # Block: Power LED schematic
# # -------------------------------------------------------------

# # 1) Add +3.3V power symbol at top
# add_power_symbol("+3.3V", "#PWR_3V3", 150, 120)

# # 2) Add resistor R4 (1 kΩ) below +3.3V
# add_RLC_symbol("R", 150, 100, "R4", "1K")

# # 3) Add LED D1 (RED) rotated 90° for vertical orientation
# add_schematic_symbol("Device", "LED", 150, 88, reference="D1", value="RED", rotation=90)

# # 4) Add GND power symbol at bottom
# add_power_symbol("GND", "#PWR_GND", 150, 76)

# # # 5) Wiring connections
# # # Connect +3.3V power to R4 pin 1
# # add_new_wire(get_pin_location("#PWR_3V3", "1"), get_pin_location("R4", "1"))

# # # Connect R4 pin 2 to LED anode (pin "A")
# # add_new_wire(get_pin_location("R4", "2"), get_pin_location("D1", "A"))

# # # Connect LED cathode (pin "K") to GND
# # add_new_wire(get_pin_location("D1", "K"), get_pin_location("#PWR_GND", "1"))

# get_pin_location("D1", "A")
# get_pin_location("D1", "K")
#                                  """)

    # current_sch_img = get_sch_with_axes()

