'''
This script tests the inference of a fine-tuned Mxfp4 model for PCB schematic generation. It can run in two modes:
1) Raw mode: You provide a custom user prompt directly via command line, and the script generates a schematic based on that prompt.
2) Dataset mode: You specify a dataset file and an index, and the script uses the messages from that dataset sample as input to generate a schematic.
The generated output is expected to contain a 'final' section with the Python code for the schematic. The script extracts this section, cleans it up by removing any special tokens or Markdown formatting, and saves it as a .py file.
'''
# Load the model
import torch
from pathlib import Path
import sys
import os
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)
torch.manual_seed(42)
from transformers import Mxfp4Config
import re
from typing import Union
import argparse
import json
from schematic_generation.evaluation import get_final_python
from config import prepare_context

import sys as _sys
_argv_backup = _sys.argv[:]
_sys.argv = [_sys.argv[0]]

try:
    from datasets import load_dataset
    from modules.symbol_context import load_related_symbols, describe_symbol_info
    from modules.utils.llm_interface import GetLLMInterface
    from modules.utils.kicad_scan_lib import (
        get_sym_context_with_cache, load_organized_lib, to_lib_name_tuples
    )
    from modules.sch_evaluation import extract_meta_info
finally:
    _sys.argv = _argv_backup

project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

MAX_TOKENS = 13312

# Test Inference

# Load trained model
from transformers import AutoModelForCausalLM, AutoTokenizer, Mxfp4Config
from peft import PeftModel

# Load the tokenizer
tokenizer = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")

# load a modified chat template from a file ({% generation %} and {% endgeneration %} addded for assistant_only_loss)
new_chat_template_path = Path(project_path) / "training" /"modified_chat_template.txt"
with new_chat_template_path.open("r", encoding="utf-8") as f:
    new_chat_template = f.read()

tokenizer.chat_template = new_chat_template


# Load the original model first
quantization_config = Mxfp4Config(dequantize=True)
model_kwargs = dict(attn_implementation="flash_attention_2", torch_dtype=torch.bfloat16, use_cache=False, device_map="cuda", quantization_config=quantization_config)
base_model = AutoModelForCausalLM.from_pretrained("openai/gpt-oss-20b", **model_kwargs)

# Model will be loaded after parsing CLI arguments

symbol_selector_llm = GetLLMInterface(model_name="gpt-5.2", model_provider="Azure")

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test model inference with raw request or dataset sample.")
    g = p.add_mutually_exclusive_group(required=True)  # Force user to choose one
    g.add_argument("--test_raw", action="store_true", help="Test with a raw user request.")
    g.add_argument("--test_dataset", type=str, help="Test with a sample from the dataset.")
    p.add_argument("--prompt", type=str, default="I would like to add a USB_B connector interface in the schematic, exporting two labels, namely D+ and D-. Make the schematic as simple as possible.", help="Optional prompt for --test_raw.")
    p.add_argument("--index", type=int, default=0, help="Sample index for --test_dataset.")
    p.add_argument("--debug", action="store_true", help="Enable debug mode.")
    p.add_argument("--schematic_code", type=Path, default="schematic_generation/generated.py", help="Path to the Python schematic code file to execute in the initialized KiCad project.")
    p.add_argument("--model_path", type=str, default="microsoft/SchGen", help="Path or HuggingFace model ID for the PEFT fine-tuned model.")
    return p

def run_raw_test(prompt: str | None):
    if prompt is None:
        prompt = input("Enter prompt: ")
    print(f"[RAW] prompt={prompt}")

    selected_symbols = load_related_symbols(
        llm=symbol_selector_llm,
        sch_request=prompt,
        organized_lib_path="./export/organized_lib.json",
    )
    symbol_context = describe_symbol_info(selected_symbols)

    msg_list = prepare_context()

    msg_list.append({"role": "user", 
                    "content": f"""
                    The user request is: {prompt}
                    ###
                        We have the following symbols and their related context information as listed below: {symbol_context}
                    ###
                        When determining the rotation and mirror of a symbol, REMEMBER to refer to the symbol information and compare it with the actual connections. When determining the connections, remember to refer to the pin location of symbols you have put on the schematic before.
                        Limit your thinking process less than 1000 words.
                    """})
    
    return msg_list


def run_dataset_sample_test(index: int, dataset: str):
    # Example from GPT-oss official tutorial

    print(f"[DATASET] index={index}")
    ds = load_dataset("json", data_files={"train": dataset})["train"]
    msg_list = ds[index]["messages"][:2] # only take system and use msg as input.
    print("Loaded dataset sample messages:", msg_list[1])\
    
    return msg_list

def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.debug:
        print("[DEBUG] mode on")

    # Load the PEFT model using the provided or default model path
    peft_model_id = args.model_path
    model = PeftModel.from_pretrained(base_model, peft_model_id)
    model = model.merge_and_unload()
    model.eval()

    if args.test_raw:
        msg_list = run_raw_test(args.prompt)
    else:
        msg_list = run_dataset_sample_test(args.index, args.test_dataset)

    # Apply Chat template
    input_ids = tokenizer.apply_chat_template(
        msg_list,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(model.device)

    # Test with trained model
    output_ids = model.generate(
        input_ids,
        max_new_tokens=MAX_TOKENS,
        attention_mask=torch.ones_like(input_ids),
    )

    gen_only = output_ids[:, input_ids.shape[-1]:]
    response = tokenizer.batch_decode(gen_only, skip_special_tokens=False)[0]
    print("Model raw response:", response)
    code = get_final_python(response)

    args.schematic_code.write_text(code, encoding="utf-8")
    print(f"Saved generated code to {args.schematic_code}")


if __name__ == "__main__":
    main()