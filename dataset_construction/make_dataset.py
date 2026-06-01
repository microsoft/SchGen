"""
Coding Rules:
1. The code should be valid Python and should use the KiCad Python API. The code should contain comments, starting with #, to explain what each part does.
2. You should write the code block by block, each block is a piece of code that create a specific block/part of the schematic. For example, for a ESP32 microcontroller module, you should have one main block (including ESP32 symbols and related labels), a power block (including power symbols and related labels), a oscillator block (including crystal and related components and labels), a reset block (including reset button and related components and labels), etc. Each block should be separated by a comment line with the block name. Use labels to connect the blocks together, so that the schematic is easy to read and understand. Do NOT wire everything together with long wires, as that is hard to read. Make sure each block is self-contained with proper labels as interfaces and can be understood independently.
3. When generating the code of each block, you should follow the following order:
- Step 1: Specify the coordinates of the center symbol of each block, the center symbol is the one with the most pins.
- Step 2: First add the center symbol, then add other symbols of coordinates with respect to the center symbol.
- Step 3: Add label and connect them to the nearby related pins.
- Step 4: Connect all wires in the schematic with component and pin specified.
After finishing draw all blocks, write out all wires.
4. To allow enough space between components and symbols, you should use a minimum of 10mm spacing between components. For example, if you place a component with a pin at (100, 100), the next component should be placed at least at (110, 100) or further away. The power symbols and labels can be placed closer to the components, but still should not overlap with other components or wires.
"""

# This code is used to make the jsonl dataset for gpt-oss finetuning
import json
import tqdm
from pathlib import Path
import re
import sys
import os

os.environ["MPLBACKEND"] = "Agg"

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import sqlite3
import argparse

proj_path = os.environ["PROJECT_PATH"]
sys.path.append(proj_path)

from modules.kicad_sch_interface import reY, RAISE_ERR_FLAG, REVERSE_Y_FLAG
from modules.utils.kicad_sch_export import get_sch_with_axes, get_schematic_netlist
from modules.utils.llm_interface import GetLLMInterface
from modules.utils.kicad_scan_lib import load_organized_lib
from modules.symbol_context import get_symbol_context
import my_skip_lib

"""
L1: Relative position + pin connection
L2: Absolute position + pin connection
L3: Absolute position + direct wire 
"""

code_representation_level = "L1"

REPRESENTATION_LEVEL_RE = re.compile(r"_(L[123])$", re.IGNORECASE)

sch_type = "sch"
BASE_DIR = "" # Root Directory
reasoning_level = "medium"
OUT_JSONL = Path(os.path.join(proj_path, f"jsonl_dataset/new_form/finetune_dataset_{sch_type}_{code_representation_level}.jsonl")) # Output JSONL file of the dataset
NUM_WORKERS = 1 # Number of workers (adjust based on API / I/O capabilities)
MAX_SAMPLES = None # For debugging, max number of schematics to process; None means all

def _unq(s):
    """Get the unique name of a symbol."""
    if isinstance(s, str):
        s = s.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1]
    return s

# Define the LLM interface

llm_gpt5 = GetLLMInterface(model_name="gpt-5.2", model_provider="Azure")
llm_oss_20b = GetLLMInterface(model_name="gpt-oss-20b", model_provider="OpenRouter")
llm_oss_120b = GetLLMInterface(model_name="gpt-oss-120b", model_provider="Azure")

# Load the organized library of KiCAD
sym_lib_dict = load_organized_lib()

# Define the query at different levels
q_concise = "Assume you are a customer with a need of PCB schematic design, based on the given schematic and its netlist, summarize its high-level function with an output of just one sentence that describe your requirement, e.g., I want an LED driven by 3.3V and controlled by a switch."

q_detailed = "Assume you are a customer with a need of PCB schematic design, based on the given schematic and its netlist, describe its functionality in detail, including all specific symbols, labels and their connections in the form your requirement, e.g., I want an IMU module with the chip of ICM-20948 as U2, one 1.8v rail, 4 gnd rails, 3 capacitors with C1: 1.0 uF, C2: 0.1 uF, C3: 0.1 uF and 6 labels. U2 pin 1 is connected to the 1.8V rail, C1 pin 1, C2 pin 1, C3 pin 1, U2 pin 3 is connected to label INT, ... Note that you need to be sound like an actual human customer, make the generated request smooth and readable."


def parse_code_representation_level(sch_path: Path) -> str:
    """Infer the representation level from the schematic filename."""
    match = REPRESENTATION_LEVEL_RE.search(sch_path.stem)
    if match:
        return match.group(1).upper()
    return code_representation_level


def prepare_context(code_level: str):
    # Load few-shot examples from the files

    example_code_files = [
        f"imu_{code_level}.py",
    ]

    # Switch that determine whether to add example code
    add_example_code = 1

    if add_example_code:
        example_codes = []
        for sch_name in example_code_files:
            filename = os.path.join(proj_path, "schematic_generation/sch_examples", sch_name)
            if not os.path.exists(filename):
                raise FileNotFoundError(f"Example file {filename} does not exist.")
            with open(filename, "r") as f:
                example_code = f.read()
                example_codes.append(example_code)

        example_code_str = "\n\n".join(example_codes)

    msg_list = [
        {"role": "system",
        "content": f"""
        Reasoning:{reasoning_level}\n
        You need to complete a user request by outputting executable Python code that generates a KiCad schematic file corresponding to the request. Generate the Python code to edit the schematic file using the KiCad Python API. YOU MUST MAKE SURE THE FINAL CODE ALIGN WITH THE THINKING PROCESS.
        ###
        You have the following functions available to you and can create new functions based on them:
        - def add_schematic_symbol(symbol_lib="RF_Module", symbol_name="ESP-WROOM-02", pos_x=150, pos_y=100, reference="U1", value="", rotation=0, mirror:str =None): Add any component symbol from a KiCad library into your schematic. The symbol_lib and symbol_name specify the library and symbol name of the component to add. The pos_x and pos_y specify the position of the center of the symbol in mm. The reference is the unique identifier for the component, e.g., "U1", "R1", "C1". The value is the value of the component, e.g., "10K", "100nF", "ESP32". The rotation is the angle in degrees to rotate the symbol, e.g., 0, 90, 180, 270. The mirror can be "X" or "Y" to flip the symbol according to X or Y axis. If mirror is None, no mirroring is applied.
        NOTE:If there is no related information for value, you need to set a value based on your knowledge about what the schematic design. For example, for a pull up resistor, you can set a value of "10K", for a decoupling capacitor, you can set a value of "100nF". value string should NOT include space or `()` or use `TBD`, for example, `12pF (NC)` should be set as "12pF", and `10K (pull up)` should be set as "10K". 

        - def get_pin_location(symbol_ref: str, pin_name: str): Get the location of a pin in the schematic. Args: symbol_ref (str): The reference of the symbol or label. pin_name (str): The name or id of the pin, for power symbol or label, this should be "1".

        - def add_label(label_pos: list, label_text: str, label_ref: str, label_type: str = "input", text_orient: str ="left"): Add a label to the schematic. The label_pos is a list of two floats [x, y] specifying the position of the label's pin in mm. The label_text is the text of the label, e.g., "IO1", "SDA", "RXD". The label_ref is the unique identifier for the label, e.g., "IO1_0", "SDA_0", "SDA_1". The label_type can be "input", "output", "bidirectional" to specify the type of the label. The text_orient can be "left", "right", "top", or "bottom" to specify the orientation of the text relative to the label pin position.

        """
        + ("""
        - def add_new_wire(start: list, end: list). Add a wire between two points in the schematic. The start and end are lists of two floats [x, y] specifying the start and end positions of the wire in mm.
        """ if code_representation_level == "L3" else """- def connect_pins(sym_a: str, pin_a: str, sym_b: str, pin_b: str). Create a connection between pin_a of symb_a and pin_b of sym_b. The sym_a and sym_b are the references of the symbols or labels to connect. The pin_a and pin_b are the names or ids of the pins to connect. Note: We treat labels as a kind of symbols, identified by their unique reference. For power symbols and labels, they only have one pin, so pin_a or pin_b should be "1".""") + 
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

from typing import Optional

def read_code(sch_path: Path) -> tuple[Optional[str], Optional[Path], str]:
    """
    Read code from a .py file corresponding to a schematic base name.
    Supports:
      - sch_0_0_L1.py
      - sch_0_0_L2.py
      - sch_0_0_L3.py
    """
    base_dir = sch_path.parent
    base = sch_path.stem if sch_path.suffix else sch_path.name
    code_level = parse_code_representation_level(sch_path)

    candidate_names = [
        f"{base}_{code_level}.py",
    ]

    for name in candidate_names:
        p = base_dir / name
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="replace")
            return text, p, code_level

    return None, None, code_level

from typing import Iterable
def iter_all_schematics(base_dir: Path, output_jsonl: Path) -> Iterable[Path]:
    """
    Iterate through all legal schematic files in base_dir, skipping any file
    whose absolute path already appears in the JSONL's meta.schematic_path.
    """
    # 1) Load processed schematic paths from existing JSONL (if any)
    processed = set()
    if output_jsonl and output_jsonl.exists():
        with output_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                meta = obj.get("meta") or {}
                sp = meta.get("schematic_path")
                if not sp:
                    continue
                try:
                    processed.add(Path(sp).resolve())
                except Exception:
                    # If path cannot be resolved for any reason, keep as-is best effort
                    processed.add(Path(sp))

    # 2) Yield unprocessed schematics
    for module_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        for sch_path in sorted(module_dir.glob("sch_*_*.kicad_sch")):
            name = sch_path.name
            if sch_path.resolve() in processed:
                continue
            yield sch_path

def build_sym_infos(sch, sym_lib_dict):
    """Build symbol information list from schematic."""
    sym_infos = []
    sym_list = []
    visited_lib_ids = set()
    for component in getattr(sch, "symbol", []):
        lib_id = getattr(component.lib_id, "value", None)
        if not lib_id or lib_id in visited_lib_ids:
            continue
        visited_lib_ids.add(lib_id)

        if ":" in lib_id:
            symbol_lib, symbol_name = lib_id.split(":", 1)
        else:
            symbol_lib, symbol_name = lib_id, ""

        sym_list.append( (symbol_lib, symbol_name) )

        for sym_info in sym_lib_dict.get(symbol_lib, []):
            if _unq(sym_info.get("name", "")) == symbol_name:
                tmp = dict(sym_info)
                tmp["symbol"] = ""     
                tmp["datasheet"] = ""  
                # tmp["footprint"] = ""
                sym_infos.append(tmp)
                break
    return sym_list, sym_infos

# Regular expressions for extracting final segments
_FINAL_BLOCK_RE = re.compile(
    r"<\|channel\|>\s*final\s*<\|message\|>(.*?)(?:(?:<\|channel\|>|<\|end\|>|$))",
    re.S | re.I
)
# remove <return>
_RETURN_SUFFIX_RE = re.compile(r'(?:\s*<\|return\|>\s*)+$', re.S)

def extract_final(text: str) -> str:
    """
    Extract the <final> from the original response
    """
    m = _FINAL_BLOCK_RE.search(text)
    segment = m.group(1) if m else text
    segment = _RETURN_SUFFIX_RE.sub('', segment).strip()
    return segment

def get_thinking_attribute(request: str, output: str, model_name: str, code_level: str):
    """
    Generate thinking process of the agent using local LLM
    """
    msg = prepare_context(code_level)
    prompt = (f"There is the following user request: {request}\n"
              f"And the corresponding output is: {output}\n"
              f"You need to output the thinking process from the request to the output." 
              f"The thinking process should first reason about overall request, then describe the physical connections of the schematic in the output code, then cover the code in the output line by line to explain the thinking process leading to the code. (Note that DO NOT directly copy python code in the output above, FOCUS on the logic behind the code). The thinking explanation should cover all the function arguments, especially, symbol name, spatial placement (for symbols, location, reference pin location, relative coordinate offset, rotation, mirror, for labels, label_pos and text_orient), label to pin wire connections, pin to pin wire connections. For wire connections, the thinking should cover why certain pins are connected to achieve overall function, for example, to light up an LED, pin 1 (K) of LED should connect with low voltage like GND. For rotations and mirrors, you should explain why specific value can make the wire connections easier and schematic more readable.\n"
              f"The total output should be less than 1000 words."
              )
    msg.append({"role": "user", "content": prompt})
    if model_name == "gpt-20b":
        response =  llm_oss_20b.get_string_response(msg)
    elif model_name == "gpt-120b":
        response = llm_oss_120b.get_string_response(msg)
    return extract_final(response)

def make_samples(sch_path: Path) -> list[dict]:
    """
    Generate concise and detailed samples from a schematic.
    """

    module_name = sch_path.parent.name
    code_level = parse_code_representation_level(sch_path)

    # 1) Analyze the schematic
    sch = my_skip_lib.Schematic(sch_path)
    if not getattr(sch, "symbol", []): 
        return []

    # 2) Symbol information (CACHED)
    sym_context = get_symbol_context(sch)

    # 3) Image & netlist
    sch_img = get_sch_with_axes(image_name=f"sch_with_axes_{module_name}_{sch_path.stem}.png", schematic_path=sch_path)
    netlist = get_schematic_netlist(sch_path, "export/temp_sch.net")

    # 4) Generate prompt
    prompt_concise = (
        f"You are given the following request from the user: {q_concise}\n"
        f"Please refer to the netlist of the schematic: {netlist} and the image below "
        f"to generate the response to the request. Please do not include any details and "
        f"DIRECTLY generate the response with just ONE SENTENCE."
    )
    prompt_detailed = (
        f"You are given the following request from the user: {q_detailed}\n"
        f"Please refer to the netlist of the schematic: {netlist} and the image below "
        f"to generate the response to the request."
    )

    # 5) Call the LLM (image + text)
    inp_concise = llm_gpt5.prepare_input_with_image(prompt_concise, sch_img)
    inp_detailed = llm_gpt5.prepare_input_with_image(prompt_detailed, sch_img)
    msg_concise = llm_gpt5.get_string_response(inp_concise)
    msg_detailed = llm_gpt5.get_string_response(inp_detailed)

    # Attach symbol information
    msg_concise += f"\nYou MUST USE the following symbol information from KiCad library: {sym_context}."
    msg_detailed += f"\nYou MUST USE the following symbol information from KiCad library: {sym_context}."

    # 6) basic system input
    ctx_concise_1 = prepare_context(code_level)
    ctx_detailed_1 = prepare_context(code_level)

    ctx_concise_2 = prepare_context(code_level)
    ctx_detailed_2 = prepare_context(code_level)

    # 7) user input
    ctx_concise_1.append({"role": "user", "content": msg_concise})
    ctx_detailed_1.append({"role": "user", "content": msg_detailed})

    ctx_concise_2.append({"role": "user", "content": msg_concise})
    ctx_detailed_2.append({"role": "user", "content": msg_detailed})

    # 8) Standard output: Read the same-name .py code as assistant content
    code_text, code_path, parsed_level = read_code(sch_path)
    if not code_text:
        return []

    code_level = parsed_level

    # 9) Generate the standard output from gpt-2ob (local) and gpt-120b
    thinking_concise_1 = get_thinking_attribute(msg_concise, code_text, "gpt-120b", code_level)
    thinking_detailed_1 = get_thinking_attribute(msg_detailed, code_text, "gpt-120b", code_level)

    thinking_concise_2 = get_thinking_attribute(msg_concise, code_text, "gpt-20b", code_level)
    thinking_detailed_2 = get_thinking_attribute(msg_detailed, code_text, "gpt-20b", code_level)

    ctx_concise_1.append({"role": "assistant", "content": code_text, "thinking": thinking_concise_1})
    ctx_detailed_1.append({"role": "assistant", "content": code_text, "thinking": thinking_detailed_1})

    ctx_concise_2.append({"role": "assistant", "content": code_text, "thinking": thinking_concise_2})
    ctx_detailed_2.append({"role": "assistant", "content": code_text, "thinking": thinking_detailed_2})

    # 10) Return the samples
    meta = {
        "module": module_name,
        "schematic": sch_path.name,
        "schematic_path": str(sch_path),
        "code_path": str(code_path) if code_path else None,
    }
    return [
        {"messages": ctx_concise_1, "meta": {**meta, "thinking_model": "gpt-oss-120b" ,"style": "concise"}},
        {"messages": ctx_detailed_1, "meta": {**meta, "thinking_model": "gpt-oss-120b" ,"style": "detailed"}},
        {"messages": ctx_concise_2, "meta": {**meta, "thinking_model": "gpt-oss-20b" ,"style": "concise"}},
        {"messages": ctx_detailed_2, "meta": {**meta, "thinking_model": "gpt-oss-20b" ,"style": "detailed"}},
    ]

def build_jsonl_dataset(base_dir: Path, out_jsonl: Path, num_workers: int = 8, max_samples=None):
    """
    Parallel process schematic files and write to JSONL. Each line is a sample: {"messages":[...], "meta":{...}}
    """
    # Collect all schematic paths
    all_paths = list(iter_all_schematics(base_dir, out_jsonl))
    print(f"[INFO] Total schematics to process: {len(all_paths)}")
    if max_samples is not None:
        all_paths = all_paths[:max_samples]

    print(f"[INFO] Found {len(all_paths)} schematics under {base_dir}")

    # Output file preparation
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    write_lock = Lock()
    total_ok = 0
    total_err = 0

    with ThreadPoolExecutor(max_workers=num_workers) as ex, out_jsonl.open("a", encoding="utf-8") as fout:
        futures = {ex.submit(make_samples, p): p for p in all_paths}

        for fut in as_completed(futures):
            sch_path = futures[fut]
            try:
                samples = fut.result()
                if not samples:
                    print(f"[WARN] No samples generated for {sch_path}")
                    total_err += 1
                    continue
                else:
                    print(f"[INFO] Generated {len(samples)} samples for {sch_path}")
                # Write to file (with lock)
                with write_lock:
                    for s in samples:
                        fout.write(json.dumps(s, ensure_ascii=False) + "\n")
                total_ok += len(samples)
            except Exception as e:
                total_err += 1
                print(f"[ERROR] {sch_path}: {e}\n{traceback.format_exc()}")

    print(f"[DONE] Wrote {total_ok} samples to {out_jsonl} (errors: {total_err})")


def write_samples_to_jsonl(schematic_path: Path, out_jsonl: Path):
    """Generate samples for one schematic and write them to a JSONL file."""
    samples = make_samples(schematic_path)
    if not samples:
        print(f"[WARN] No samples generated for {schematic_path}")
        return 0

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("a", encoding="utf-8") as fout:
        for sample in samples:
            fout.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"[DONE] Wrote {len(samples)} samples to {out_jsonl}")
    return len(samples)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build JSONL dataset from KiCad schematics.")
    parser.add_argument("-s", "--schematic_path", type=str, help="Path to a single schematic file to process")
    parser.add_argument("-o", "--out_jsonl", type=str, help="Path to the output JSONL file")
    parser.add_argument("--num_workers", type=int, default=NUM_WORKERS, help="Number of worker threads for batch mode")
    parser.add_argument("--max_samples", type=int, default=MAX_SAMPLES, help="Maximum schematics to process in batch mode")
    args = parser.parse_args()

    if args.schematic_path and args.out_jsonl:
        write_samples_to_jsonl(Path(args.schematic_path), Path(args.out_jsonl))
    else:
        build_jsonl_dataset(BASE_DIR, OUT_JSONL, num_workers=args.num_workers, max_samples=args.max_samples)
    # make_samples(Path("/home/v-luoqinpei/workspace/llm4circuit/dataset/15335_9DoF_Schematic/sch_0_0.kicad_sch"))
