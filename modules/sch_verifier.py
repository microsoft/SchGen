import os, sys
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

from pathlib import Path

from modules.sch_module_def import *

from modules.kicad_sch_interface import load_schematic, save_schematic

from modules.utils.kicad_sch_export import get_sch_with_axes, get_schematic_netlist

from modules.utils.llm_interface import GetLLMInterface

from modules.utils.custom_logger import setup_logger

from modules.utils.misc import *



class SchematicVerifier():
    def __init__(self, model_name="o4-mini", model_provider="Azure"):
        self.logger = setup_logger()
        self.logger.info(f"Initializing SchematicVerifier ")
        self.llm = GetLLMInterface(model_name=model_name, model_provider=model_provider)
 
    def visual_verify(self, user_request: str, img_ref_path: str = None) -> str:
        """
        Verify the schematic visually based on the user's request and reference image if available.
        """

        # 1. extract the schematic image.
        sch_img_path = get_sch_with_axes()
        self.logger.info(f"Schematic image extracted. {sch_img_path}")

        # 2. Use LLM to provide feedback on the schematic image.
        sch_vision_question = f"""
        Check the kicad schematic image and provide feedback about whether it meets the following user request:
        {user_request}
        If there are two images provided below, you should use the second one as ground truth reference image and compare the first one with the second one for any errors or warnings.
        ###
        There are two levels of feedback: warnings and errors.
        Error include electrical connection errors like short circuit, open circuit, circuit component overlay, or the current design conflicts with or fail to follow the user request.
        Warning include design issues like misaligned component placement, unreadable wire connections, that can be improved to create a better schematic design but not errors.
        ###
        Output format:
        1. First, provide a score from -1, 0, or 1, where -1 means the schematic is not correct, 0 means the schematic is correct but can be improved, and 1 means the schematic is correct and well-designed.
        2. Then, provide a list of errors and warnings.
        3. Finally, provide suggestions to fix the errors and warnings. Be specific about the suggested operations, such as the specific numbers of positions, orientation moves.
        ###
        Important NOTE:
        1. Focus on the image. Think carefully about the schematic, do not provide feedback unless you are sure about the issues.
        2. The dashed lines in the image is for reading the coordinates only. Dashed lines are not part of the schematic and should not be considered as wires.
        3. It is correct and encouraged to use multiple same valued net/global label or power symbols to simplify the schematic design. For example, if there are multiple GND pins, you can use multiple GND symbols to connect them together, so that no long wires are needed.
        4. Common errors include: (1) Components or symbols overlap with each other. For example, placing a GND or power symbol inside the rectangle of another symbol is an error. Adjust the component placement and wiring to correct the schematic.  
        5. Some common issues are: (1) placing the components too close to each other. (2) wire goes through the component and create overlay. A wire goes through a component symbol is a warning, you should suggest a different wiring path to avoid the wire going through the component symbol.
        """        
        # self.msg_list.append({"role": "user", "content": sch_vision_question})

        if img_ref_path is not None:
            image_msg = self.llm.prepare_input_with_images(sch_vision_question, [sch_img_path, img_ref_path])
        else:
            image_msg = self.llm.prepare_input_with_images(sch_vision_question, [sch_img_path])
        assert isinstance(image_msg, list) and len(image_msg) == 1, "Image message should be a list."

        # 3. return the feedback from LLM
        # response = self.llm.get_string_response(self.msg_list)
        response, feedback_obj = self.llm.get_json_response_retry(image_msg, VisionFeedbackDef)
        self.logger.info(f"Schematic Verifier visual feedback Response: {response}")

        return response, feedback_obj


    def netlist_verify(self, user_request: str, img_ref_path: str = None, img_description: str = None, schematic_path: str = None) -> str:
        """
        Verify the schematic netlist based on the user's request.
        """
        
        # Get the netlist for the schematic
        netlist = get_schematic_netlist(sch_file=schematic_path, netlist_file="export/temp_sch.net")

        self.logger.info(f"User request for netlist verification: {user_request}")
        self.logger.info(f"Schematic netlist extracted. {netlist}")

        netlist_veri_question = f"""
        Check the netlist of a KiCAD schematic and verify whether it meets the following user request:
        {user_request}
        ###
        Netlist of the schematic:
        {netlist}
        If there is a reference image provided below, you should use the image and its description {img_description} as ground truth reference and compare the netlist with the image for any errors or warnings. 
        ###
        There are two levels of feedback: warnings and errors.
        ###
        Output format:
        1. If a reference image is provided, provide a KiCAD netlist file content that matches the image exactly. If no reference image below, skip this step.
        2. Check the user request together with the reference image above, compare with the schematic netlist provided for any errors or warnings.
        3. provide a score from -1, 0, or 1, where -1 means the schematic is not correct, 0 means the schematic is correct but can be improved, and 1 means the schematic is correct and well-designed.
        2. Then, provide a list of errors and warnings.
        3. Finally, provide suggestions to fix the errors and warnings. Be specific about the suggested operations, such as the specific numbers of positions, orientation moves.
        ###
        Important NOTE:
        1. Focus on the netlist. Think carefully about the schematic, do not provide feedback unless you are sure about the issues.
        2. It is correct and encouraged to use multiple same valued net/global label or power symbols to simplify the schematic design. For example, if there are multiple GND pins, you can use multiple GND symbols to connect them together, so that no long wires are needed.
        3. If you encounter any symbol with a shape of splited circle/disc/pad, it means they are solder jumper. DIRECTLY OMIT them along with the text description aside and consider them as just WIRES.
        4. Note that labels are defintely rectangle or pentagon shapes, DO NOT confuse them with text descriptions.
        """

        if img_ref_path is not None:
            image_msg = self.llm.prepare_input_with_image(netlist_veri_question, img_ref_path)
        else:
            image_msg = [{
                "role": "user",
                "content": netlist_veri_question,
            }]
        assert isinstance(image_msg, list) and len(image_msg) == 1, "Image message should be a list."

        # 3. return the feedback from LLM
        # response = self.llm.get_string_response(self.msg_list)
        response, feedback_obj = self.llm.get_json_response_retry(image_msg, NetlistFeedbackDef)
        self.logger.info(f"Schematic Verifier netlist feedback Response: {response}")

        return response, feedback_obj

    def netlist_verify_sch(self, user_request: str, standard_netlist: str) -> str:
        """
        Verify the schematic netlist based on the user's request.
        """
        
        # Get the netlist for the schematic
        netlist = get_schematic_netlist()

        self.logger.info(f"User request for netlist verification: {user_request}")
        self.logger.info(f"Schematic netlist extracted. {netlist}")

        netlist_veri_question = f"""
        Check the netlist of a KiCAD schematic and verify whether it meets the following user request:
        {user_request}
        ###
        Netlist of the schematic:
        {netlist}
        You should use the schematic {standard_netlist} as ground truth reference and compare the netlist with the schematic for any errors or warnings. 
        ###
        There are two levels of feedback: warnings and errors.
        ###
        Output format:
        1. If a reference schematic is provided, provide a KiCAD netlist file content that matches the schematic exactly. If no reference schematic below, skip this step.
        2. Check the user request together with the reference schematic above, compare with the schematic netlist provided for any errors or warnings.
        3. provide a score from -1, 0, or 1, where -1 means the schematic is not correct, 0 means the schematic is correct but can be improved, and 1 means the schematic is correct and well-designed.
        2. Then, provide a list of errors and warnings.
        3. Finally, provide suggestions to fix the errors and warnings. Be specific about the suggested operations, such as the specific numbers of positions, orientation moves.
        ###
        Important NOTE:
        1. Focus on the netlist. Think carefully about the schematic, do not provide feedback unless you are sure about the issues.
        2. It is correct and encouraged to use multiple same valued net/global label or power symbols to simplify the schematic design. For example, if there are multiple GND pins, you can use multiple GND symbols to connect them together, so that no long wires are needed.
        """

        image_msg = [{
                "role": "user",
                "content": netlist_veri_question,
            }]
        assert isinstance(image_msg, list) and len(image_msg) == 1, "Image message should be a list."

        # 3. return the feedback from LLM
        # response = self.llm.get_string_response(self.msg_list)
        response, feedback_obj = self.llm.get_json_response_retry(image_msg, NetlistFeedbackDef)
        self.logger.info(f"Schematic Verifier netlist feedback Response: {response}")

        return response, feedback_obj


    def verify_schematic(self, user_request: str, img_ref_path: str = None) -> str:
        """
        Verify the schematic based on the user's request and reference image if available.
        """
        
        response, feedback_obj = self.visual_verify(user_request, img_ref_path)

        response, feedback_obj = self.netlist_verify(user_request)


        # TODO: Combine the responses from visual and netlist verification
        return response + response
    

if __name__ == "__main__":
    # Example usage
    user_request = "Draw a connector that has 4 pins and connections to components as shown in the image. "
    # img_ref_path = None  # "./testing_kicad_proj/esp32_wroom_32e.png"
    img_ref_path = "./testing_kicad_proj/connector1x4.png"

    verifier = SchematicVerifier()
    response = verifier.verify_schematic(user_request, img_ref_path)
    print(response)