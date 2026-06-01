## Evaluate different models on a common test set

import torch
from pathlib import Path
import sys
import os
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)
from modules.utils.llm_interface import GetLLMInterface
from kicad_read_sch import code_generator
from typing import Dict, Any
import io
from contextlib import redirect_stdout, redirect_stderr
import re
from typing import Union
from datasets import load_dataset
import random
import json
import csv
from datetime import datetime
# Set random seed for reproducibility
SEED = 20250919
random.seed(SEED)
try:
    import numpy as np
    np.random.seed(SEED)
except Exception:
    pass
try:
    import torch
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
except Exception:
    pass

project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

torch.manual_seed(42)
from transformers import Mxfp4Config
from modules.utils.kicad_scan_lib import get_sym_context_with_cache, load_organized_lib, to_lib_name_tuples
from modules.sch_evaluation import SchematicVerifier, extract_meta_info, evaluation

MAX_TOKENS = 13312
<<<<<<< HEAD
model_names = ["grok"]  # "o4-mini", "gpt5", "grok"
=======
model_names = ["gpt-5", "o4-mini", "grok"]  # "o4-mini", "gpt5", "grok"
>>>>>>> 8df8b541cd6760342ab5afbd5dedfe0e526a0b47
RANDOM_SAMPLING = True

# Load trained model
from transformers import AutoModelForCausalLM, AutoTokenizer, Mxfp4Config
from peft import PeftModel
import tempfile

from pydantic import BaseModel
class SchematicEditCode(BaseModel):
    explanation: str
    code: str

# Load the tokenizer
tokenizer = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")

# load a modified chat template from a file ({% generation %} and {% endgeneration %} addded for assistant_only_loss)
new_chat_template_path = Path(project_path) / "modified_chat_template.txt"
with new_chat_template_path.open("r", encoding="utf-8") as f:
    new_chat_template = f.read()

tokenizer.chat_template = new_chat_template

def save_jsonl(path: str, items):
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

def get_final_sch(decoded: str) -> Path:
    """
    Extract the 'final' section from a decoded model output, strip trailing
    <|return|> markers and Markdown code fences, then save as a .py file.

    Parameters
    ----------
    decoded : str
        Full decoded text from the model (DO NOT skip special tokens before calling).
    out_path : str | Path, optional
        Destination .py path. Defaults to "./generated.py".

    Returns
    -------
    Path
        The path where the Python code was saved.
    """

    # 1) Extract content after <|channel|>final<|message|> and before next marker/end
    final_block_re = re.compile(
        r"<\|channel\|>\s*final\s*<\|message\|>(.*?)(?:(?:<\|channel\|>|<\|end\|>|$))",
        re.S | re.I
    )
    m = final_block_re.search(decoded)
    segment = m.group(1) if m else decoded

    # 2) Remove trailing <|return|> markers (possibly repeated) and trim spaces
    return_suffix_re = re.compile(r'(?:\s*<\|return\|>\s*)+$', re.S)
    segment = return_suffix_re.sub('', segment).strip()

    # 3) Remove Markdown code fences like ```python ... ``` or ``` ... ```
    code_fence_re = re.compile(r"^\s*```(?:[Pp]ython)?\s*\n|\n\s*```\s*$", re.S)
    sch_text = code_fence_re.sub("", segment).strip()

    return sch_text

def write_kicad_sch(target_path: str, content: str) -> None:
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

def run_batch_evaluation(
    jsonl_path: str,
    out_dir: str = "eval_runs",
    model_name: str = None,
):

    # Load the original model first
    llm = GetLLMInterface(model_name=model_name, model_provider="Azure")

    def save_csv(path: str, items):
        if not items:
            return
        rows = []
        # Store netlist_evaluation as JSON string to avoid nested structure in CSV
        for it in items:
            row = dict(it)
            nle = row.pop("netlist_evaluation", None)
            row["netlist_evaluation_json"] = json.dumps(nle, ensure_ascii=False) if nle is not None else ""
            rows.append(row)
        fieldnames = sorted({k for r in rows for k in r.keys()})
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_jsonl = os.path.join(out_dir, f"eval_results_raw_{model_name}.jsonl")
    out_csv   = os.path.join(out_dir, f"eval_results_raw_{model_name}.csv")

    # Check if out_csv already exists
    # if os.path.exists(out_csv):
    #     print(f"Skipping existing evaluation for model {model_name}.")
    #     return

    ds = load_dataset("json", data_files=jsonl_path, split="train")
    results = []
    # 4) Eval + streaming save
    passed_cnt = 0
    total_errors = 0
    results = []  # ，；

    # （）
    jsonl_fp = open(out_jsonl, "w", encoding="utf-8")
    csv_fp = open(out_csv, "w", newline="", encoding="utf-8")
    csv_writer = None  # （）

    try:
        for i in range(len(ds)):

            module_name, schematic_name, meta = extract_meta_info(ds[i])
            line = ds[i]
            msg_list = ds[i]["messages"][:2]  # only take system and use msg as input.

            sch_path = Path(project_path) / "export" / f"{model_name}" / f"test_code_{module_name}_{schematic_name}.kicad_sch"
            code_path = sch_path.with_suffix(".py")
            if sch_path.exists():
                sch = sch_path.read_text(encoding="utf-8")
                print(f"[{i+1}/{len(ds)}] Skipping existing schematic: {sch_path}")
                try:
                    generator = code_generator(module_name, sch_path, code_path)
                    lines = generator.work()
                    code = code_path.read_text(encoding="utf-8")
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
                    errors = sum(1 for line in combined.splitlines() if "error" in line.lower())
                    print(f"  (Detected {errors} Error lines during code execution)")
                except Exception as e:
                    print("ERROR during code execution: ", e)
            else:
                # Apply Chat template
<<<<<<< HEAD
                response, sch_obj = llm.get_json_response_retry(msg_list, SchematicEditCode)
                sch = sch_obj.code.replace("\\\"", "\"").replace("\\n", "\n")
                write_kicad_sch(sch_path, sch)
                errors = 0
=======
                continue
>>>>>>> 8df8b541cd6760342ab5afbd5dedfe0e526a0b47

            try:
                verifier = SchematicVerifier(module_name, schematic_name, model_name="o4")
                netlist_evaluation = verifier.netlist_verify(schematic_path=sch_path)
                ev = {"passed": 1, "netlist_evaluation": netlist_evaluation, "errors": errors, "exception": None}
            except Exception as e:
                print("ERROR: ", e)
                ev = {"passed": 0, "netlist_evaluation": None, "errors": 0, "exception": str(e)}

            # Get the evaluation results
            passed_cnt += int(bool(ev.get("passed", 0)))

            #  errors（）
            if isinstance(ev.get("errors", 0), int):
                total_errors += ev["errors"]

            # 
            rec = {
                "test_idx": i,                 # Sampling order from 1..k
                "module_name": module_name,
                "schematic_name": schematic_name,
                "passed": int(bool(ev.get("passed", 0))),
                "errors": ev.get("errors", None),
                "netlist_evaluation": ev.get("netlist_evaluation", None),
                "exception": ev.get("exception", None),
            }

            # ----  JSONL ----
            jsonl_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

            # ----  CSV（）----
            if csv_writer is None:
                fieldnames = list(rec.keys())
                csv_writer = csv.DictWriter(csv_fp, fieldnames=fieldnames)
                csv_writer.writeheader()
            csv_writer.writerow(rec)

            jsonl_fp.flush()
            csv_fp.flush()

    finally:
        jsonl_fp.close()
        csv_fp.close()

    # 6) Summary
    print(f"  Passed: {passed_cnt}/{len(ds)}  ({passed_cnt / len(ds):.1%})")
    print(f"  Sum(errors): {total_errors}")
    print(f"  Results JSONL: {out_jsonl}")
    print(f"  Results CSV  : {out_csv}")

    return {
        "passed": passed_cnt,
        "sum_errors": total_errors,
        "out_jsonl": out_jsonl,
        "out_csv": out_csv,
        "results": results,  # ，
    }


if __name__ == "__main__":
    eval_path = Path(project_path) / "gptoss_training" / "eval_runs"
    for i in range(len(model_names)):
<<<<<<< HEAD
        run_batch_evaluation(jsonl_path = str(Path(project_path) / "test_dataset_raw.jsonl"), out_dir=eval_path, model_name=model_names[i])
=======
        run_batch_evaluation(jsonl_path = str(Path(project_path) / "jsonl_dataset" / "test_dataset_raw.jsonl"), out_dir=eval_path, model_name=model_names[i])
>>>>>>> 8df8b541cd6760342ab5afbd5dedfe0e526a0b47
