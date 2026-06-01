# This is to set the path for the module to be imported correctly when running the script directly
if __name__ == "__main__":
    import sys
    import os
    # Use environment variable to get the project path
    project_path = os.environ["PROJECT_PATH"]
    sys.path.append(project_path)

import os
import json
import tempfile
import traceback
import io

from contextlib import redirect_stdout, redirect_stderr

from pathlib import Path

from modules.sch_module_def import *

from modules.kicad_sch_interface import load_schematic, save_schematic

from modules.utils.kicad_sch_export import get_sch_with_axes, get_schematic_netlist, get_erc_report

from modules.utils.llm_interface import GetLLMInterface

from modules.utils.custom_logger import setup_logger

from modules.utils.misc import *

from modules.utils.netlist_comparison_new import compare_netlists_sets

from modules.utils.analyze_json import extract_code, extract_meta_info, write_code

from modules.utils.santize_code import sanitize_generated_code

from typing import Any, Dict, List, Tuple

import os, sys

import re

from collections import defaultdict


TARGET_TYPES = {
    "pin_not_connected",
    "power_pin_not_driven",
    "pin_not_driven",
}

def count_erc_errors(erc_text: str):
    lines = erc_text.splitlines()

    counts = {
        "pin_not_connected": 0,
        "power_pin_not_driven": 0,
        "pin_not_driven": 0,
        "others": 0,
    }

    current_type = None
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        m = re.match(r"^\[([^\]]+)\]:", line)
        if m:
            current_type = m.group(1)

            severity = None
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                if nxt.startswith("["):
                    break
                if nxt.startswith(";"):
                    sev_match = re.match(r"^;\s*(\w+)", nxt)
                    if sev_match:
                        severity = sev_match.group(1).lower()
                    break
                j += 1

            if severity == "error":
                if current_type in TARGET_TYPES:
                    counts[current_type] += 1
                else:
                    counts["others"] += 1

        i += 1

    return counts


project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

# Functions for comparison and evaluation
DEBUG = 1

judge_llm = GetLLMInterface(model_name="gpt-5.2", model_provider="Azure")

class SchematicVerifier():
    def __init__(self, module_name, schematic_name, standard_path):

        self.logger = setup_logger()
        self.logger.info(f"Initializing SchematicVerifier ")
        self.module_name = module_name
        self.schematic_name = schematic_name
        self.standard_path = standard_path


    def netlist_verify(self, schematic_path = None) -> str:
        """
        Verify the schematic netlist and compare it with the standard output
        """
        
        # Get the netlist for the schematic
        if schematic_path == None:
            netlist = get_schematic_netlist()
        else:
            netlist = get_schematic_netlist(schematic_path)
        standard_netlist = get_schematic_netlist(self.standard_path, "schematic_standard.net")

        
        self.logger.info(f"Schematic netlist extracted. {netlist}")
        self.logger.info(f"Standard netlist extracted. {standard_netlist}")

        return compare_netlists_sets(standard_netlist, netlist)

    def get_erc_report(self, schematic_path = None) -> str:
        """
        Get the ERC report for the schematic
        """
        if schematic_path == None:
            erc_report = get_erc_report()
        else:
            erc_report = get_erc_report(schematic_path)
        
        self.logger.info(f"ERC report extracted. {erc_report}")

        return erc_report

    

KICAD_SCH_INIT = """(kicad_sch
\t(version 20231120)
\t(generator "eeschema")
\t(generator_version "8.0")
\t(uuid "f92a23cf-0bd8-4819-adfe-b8e5b9ccf1a1")
\t(paper "A4")
\t(lib_symbols)
\t(sheet_instances
\t\t(path "/"
\t\t\t(page "1")
\t\t)
\t)
)
"""

def write_kicad_sch(target_path: str, content: str = KICAD_SCH_INIT) -> None:
    """
    Overwrite the given path with KiCad .kicad_sch content.
    - Creates parent directories if missing.
    - Writes UTF-8 with LF newlines.
    - Uses atomic replace to avoid partial writes.
    """
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Create a temp file in the same directory for atomic replace on all OSes
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(p.parent), encoding="utf-8", newline="\n") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    # Atomic replace (on Windows this replaces if exists; on POSIX it's atomic)
    os.replace(tmp_path, p)  # overwrites existing file

def evaluation(data, code_path, code):

    module_name, schematic_name, meta = extract_meta_info(data)
    standard_path = meta.get("schematic_path")
    # Execute the code
    target_kicad = Path(project_path) / "export" / "test.kicad_sch"
    write_kicad_sch(target_kicad)
    print(f"[INFO] Initialized KiCad schematic of {module_name}/{schematic_name}")
    errors = 0
    code = sanitize_generated_code(code)
    try:
        filename = code_path  # keep your original filename for better traceback
        compiled = compile(code, filename, "exec")
        exec_globals: Dict[str, Any] = {}

        sys.modules.pop("modules.kicad_sch_interface", None)  # clear cached module to reset state

        exec_globals: Dict[str, Any] = {
            "__name__": "__main__",
            "__file__": filename,
        }

        # capture both stdout and stderr during execution
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            exec(compiled, exec_globals)

        # collect outputs
        out_text = buf_out.getvalue()
        err_text = buf_err.getvalue()
        combined = out_text + ("\n" if out_text and err_text else "") + err_text

        # count "second-class errors": lines that contain "error" (case-insensitive)
        # You can choose word-boundary matching; here we do a simple per-line contains to be more permissive.
        errors += sum(1 for line in combined.splitlines() if "error" in line.lower())

        if combined.strip():
            # optional: print combined output, or keep it for logs
            print(combined)

    except Exception as e:
        print(f"[ERROR] Exception during assistant code execution: {type(e).__name__}: {e}", file=sys.stderr)
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        return {"passed": 0}

    # After execution, you can report the count:

    verifier = SchematicVerifier(module_name, schematic_name, standard_path)
    evaluation = {"passed": 1}
    # Add netlist evaluation to the result
    evaluation["netlist_evaluation"] = verifier.netlist_verify()
    evaluation["errors"] = errors

    erc_report = verifier.get_erc_report(schematic_path=target_kicad)

    evaluation["erc_errors"] = count_erc_errors(erc_report)

    return evaluation

if __name__ == "__main__":
    
    # Initialize the kicad file for testing
    target_kicad = Path(project_path) / "export" / "test.kicad_sch"
    write_kicad_sch(target_kicad)

    # Read from the dataset
    path = "/home/ruichunma/workspace/llm4circuit/jsonl_dataset/new_form/finetune_dataset_sch_int_rl_medium.test.jsonl"
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                if DEBUG:
                    code = extract_code(json.loads(line))
                module_name, schematic_name, meta = extract_meta_info(json.loads(line))
                break
    
    # Execute the code
    code_path = Path(project_path) / "export" / "test.py"
    write_code(code, code_path)

    passed = 0
    # Execute the code
    errors = 0
    try:
        filename = code_path  # keep your original filename for better traceback
        compiled = compile(code, filename, "exec")
        exec_globals: Dict[str, Any] = {}

        # capture both stdout and stderr during execution
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            exec(compiled, exec_globals)

        # collect outputs
        out_text = buf_out.getvalue()
        err_text = buf_err.getvalue()
        combined = out_text + ("\n" if out_text and err_text else "") + err_text

        # count "second-class errors": lines that contain "error" (case-insensitive)
        # You can choose word-boundary matching; here we do a simple per-line contains to be more permissive.
        errors += sum(1 for line in combined.splitlines() if "error" in line.lower())

        print("[OK] Assistant code executed successfully.")
        if combined.strip():
            print("[Exec Output Captured]")
            # optional: print combined output, or keep it for logs
            print(combined)

        # keep your original pass counter
        passed += 1

    except Exception:
        print("[ERROR] Exception during assistant code execution:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(4)

    # After execution, you can report the count:
    print(f"[INFO] Assistant code execution passed {passed} without syntax errors")
    print(f"[INFO] Non-syntax errors in executing: {code_path}: {errors}")

    verifier = SchematicVerifier(module_name, schematic_name, model_name="o4")
    netlist_evaluation = verifier.netlist_verify()

    print("[INFO] Netlist evaluation result:", netlist_evaluation)

    verifier.get_erc_report(schematic_path=target_kicad)
    erc_errors, erc_error_types = count_erc_errors(verifier.get_erc_report(schematic_path=target_kicad))
    print(f"[INFO] ERC report analysis: {erc_errors} errors (filtered), types: {erc_error_types}")