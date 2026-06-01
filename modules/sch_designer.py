# This is to set the path for the module to be imported correctly when running the script directly
if __name__ == "__main__":
    import sys
    # open config file to get the project path
    with open("./configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        project_path = lines[0].strip()
        sys.path.append(project_path)

import os

from pathlib import Path

from modules.sch_module_def import *

from modules.kicad_sch_interface import load_schematic, save_schematic

from modules.utils.kicad_sch_export import get_sch_with_axes, get_schematic_netlist

from modules.utils.llm_interface import GetLLMInterface

from modules.utils.custom_logger import setup_logger

from modules.utils.misc import *



class SchematicDesigner():
    # TODO:
    def __init__(self):
        self.logger = setup_logger()
        self.logger.info(f"Initializing SchematicVerifier ")

        self.llm_o3 = GetLLMInterface(model_name="o3", model_provider="Azure")
        self.llm_o4 = GetLLMInterface(model_name="o4-mini", model_provider="Azure")

        self.llm = self.llm_o3  # Default to o3, can be changed later if needed




if __name__ == "__main__":
    # Example usage
    user_request = "Draw a connector that has 4 pins and connections to components as shown in the image. "
    # img_ref_path = None  # "./testing_kicad_proj/esp32_wroom_32e.png"
    img_ref_path = "./testing_kicad_proj/connector1x4.png"

    verifier = SchematicVerifier()
    response = verifier.verify_schematic(user_request, img_ref_path)
    print(response)