import torch
from pathlib import Path
import sys
import os
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)
from modules.utils.llm_interface import GetLLMInterface
import re
from typing import Union
from modules.utils.exec_llm_code import run_sch_edit_code
import tqdm

project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

torch.manual_seed(42)
from transformers import Mxfp4Config
from modules.sch_evaluation import SchematicVerifier, extract_meta_info, evaluation

MAX_TOKENS = 13312

RANDOM_SAMPLING = False

model_names = ["gpt-5.2", "o4-mini"]  # "o4-mini", "gpt5", "grok"
levels = ["L1"]  # "L1", "L2", "L3"

from pydantic import BaseModel
class SchematicEditCode(BaseModel):
    explanation: str
    code: str

def get_final_python(decoded: str, out_path: Union[str, Path] = "generated.py") -> Path:
    """
    Extract the 'final' section from a decoded model output, strip trailing
    <|return|> markers and Markdown code fences, ensure required header exists,
    then save as a .py file.
    """

    # 1) Extract content after <|channel|>final<|message|> and before next marker/end
    final_block_re = re.compile(
        r"<\|channel\|>\s*final\s*<\|message\|>(.*?)(?:(?:<\|channel\|>|<\|end\|>|$))",
        re.S | re.I
    )
    m = final_block_re.search(decoded)
    segment = m.group(1) if m else decoded

    # 2) Remove trailing <|return|> markers
    return_suffix_re = re.compile(r'(?:\s*<\|return\|>\s*)+$', re.S)
    segment = return_suffix_re.sub('', segment).strip()

    # 3) Remove Markdown code fences
    code_fence_re = re.compile(r"^\s*```(?:[Pp]ython)?\s*\n|\n\s*```\s*$", re.S)
    code_text = code_fence_re.sub("", segment).strip()

    # ============================================================
    # 4) Ensure required KiCad schematic header exists
    # ============================================================

    required_header = (
        "# Auto-generated schematic symbols\n"
        "import sys\n"
        "import os\n\n"
        "# Get project path and import kicad schematic interface\n"
        "PROJECT_PATH = os.environ['PROJECT_PATH']\n"
        "sys.path.append(PROJECT_PATH)\n"
        "from modules.kicad_sch_interface import *\n\n"
    )

    header_check_tokens = [
        "# Auto-generated schematic symbols",
        "from modules.kicad_sch_interface import *",
        "PROJECT_PATH = os.environ['PROJECT_PATH']",
    ]

    if not all(tok in code_text for tok in header_check_tokens):
        code_text = required_header + code_text.lstrip()

    # ============================================================
    # 5) Write to file
    # ============================================================

    out_path = Path(out_path)
    out_path.write_text(code_text, encoding="utf-8")

    return code_text

_CODE_FENCE_RE = re.compile(r"^\s*```(?:python)?\s*$", re.IGNORECASE)

def _strip_markdown_code_fences(text: str) -> str:
    """
    Remove leading/trailing Markdown code fences like:
      ```python
      ...
      ```
    Also handles multiple fences and common artifacts.
    """
    if not isinstance(text, str):
        return ""

    # Normalize newlines and remove BOM
    s = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")

    lines = s.split("\n")

    # Drop leading blank lines
    while lines and lines[0].strip() == "":
        lines.pop(0)

    # If the first non-empty line is a code fence, remove it
    if lines and _CODE_FENCE_RE.match(lines[0]):
        lines.pop(0)
        # Also drop immediate blank line after opening fence
        while lines and lines[0].strip() == "":
            lines.pop(0)

    # Drop trailing blank lines
    while lines and lines[-1].strip() == "":
        lines.pop()

    # If the last non-empty line is a closing fence, remove it
    if lines and _CODE_FENCE_RE.match(lines[-1]) or (lines and lines[-1].strip() == "```"):
        # match either ``` or ```python in case model messes up
        if lines[-1].strip().startswith("```"):
            lines.pop()

    return "\n".join(lines).strip() + "\n"


def _sanitize_and_validate_code(code: str) -> str:
    """
    Sanitizes model output into runnable Python and ensures it compiles.
    """
    s = code.replace("\\\"", "\"").replace("\\n", "\n")
    s = _strip_markdown_code_fences(s)

    # If model wrapped the *entire* content in triple backticks but with extra text,
    # try a more aggressive cleanup: remove any fence lines anywhere.
    if "```" in s:
        s2_lines = []
        for ln in s.splitlines():
            if ln.strip().startswith("```"):
                continue
            s2_lines.append(ln)
        s = "\n".join(s2_lines).strip() + "\n"

    return s


# # Load trained model
# from transformers import AutoModelForCausalLM, AutoTokenizer, Mxfp4Config
# from peft import PeftModel

# # Load the tokenizer
# tokenizer = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")

# # load a modified chat template from a file ({% generation %} and {% endgeneration %} addded for assistant_only_loss)
# new_chat_template_path = Path(project_path) / "modified_chat_template.txt"
# with new_chat_template_path.open("r", encoding="utf-8") as f:
#     new_chat_template = f.read()

# tokenizer.chat_template = new_chat_template

# # Load the original model first
# quantization_config = Mxfp4Config(dequantize=True)
# model_kwargs = dict(attn_implementation="flash_attention_2", torch_dtype=torch.bfloat16, use_cache=False, device_map="auto", quantization_config=quantization_config)
# base_model = AutoModelForCausalLM.from_pretrained("openai/gpt-oss-20b", **model_kwargs).cuda()

# # Merge fine-tuned weights with the base model
# peft_model_id = Path(project_path) / "gpt-oss-20b-pcb-schematic_0915"
# model = PeftModel.from_pretrained(base_model, peft_model_id)
# model = model.merge_and_unload()
# model.eval()

from datasets import load_dataset
import random
import json
import csv
from datetime import datetime
# Set random seed for reproducibility
SEED = 20250918
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

def save_jsonl(path: str, items):
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

def _ensure_parent(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def _load_existing_pairs_from_csv(csv_path: Path):
    pairs = set()
    if not csv_path.exists():
        return pairs
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        try:
            reader = csv.DictReader(f)
            for row in reader:
                mn = row.get("module_name")
                sn = row.get("schematic_name")
                if mn is not None and sn is not None:
                    pairs.add((mn, sn))
        except csv.Error:
            pass
    return pairs

def _open_csv_append(csv_path: Path, fieldnames):
    """
    Add opens a CSV file for appending. If the file does not exist or is empty,
    """
    _ensure_parent(csv_path)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    f = csv_path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    if not file_exists:
        writer.writeheader()
        wrote_header = True
    else:
        wrote_header = False
    return f, writer, wrote_header

def _append_jsonl(jsonl_path: Path, obj: dict):
    _ensure_parent(jsonl_path)
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def run_batch_evaluation(
    model_name: str,
    level: str,
    jsonl_path: str,
    out_dir: str,
):

    llm = GetLLMInterface(model_name=model_name, model_provider="Azure")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    out_jsonl = Path(out_dir) / f"eval_results_seed_{model_name}_{level}.jsonl"
    out_csv   = Path(out_dir) / f"eval_results_seed_{model_name}_{level}.csv"

    CODE_PATH = Path(project_path) / "export" / f"test_code_{model_name}_{level}"
    CODE_PATH.mkdir(parents=True, exist_ok=True)

    done_pairs = _load_existing_pairs_from_csv(out_csv)

    fieldnames = [
        "test_idx",
        "module_name",
        "schematic_name",
        "passed",
        "errors",
        "netlist_evaluation",
        "exception",
    ]

    csv_fh, csv_writer, _ = _open_csv_append(out_csv, fieldnames)

    passed_cnt = 0
    total_errors = 0
    total_seen = 0

    ds = load_dataset("json", data_files=jsonl_path, split="train")
    key_seen_times = {}
    try:
        for i in tqdm.tqdm(range(len(ds)), desc=f"Evaluating {model_name}"):
            total_seen += 1

            module_name, schematic_name, meta = extract_meta_info(ds[i])
            line = ds[i]
            msg_list = ds[i]["messages"][:2]  # only system + user

            key = (module_name, schematic_name)
            # Record the times the key was seen
            key_seen_times[key] = key_seen_times.get(key, 0) + 1
            # if key in done_pairs:
            #     print(f"[{i+1}/{len(ds)}] Skip (already in CSV): {module_name} / {schematic_name}")
            #     continue

            code_path = Path(CODE_PATH) / f"{module_name}_{schematic_name}_test.py"

            # if code_path.exists():
            #     print(f"[{i+1}/{len(ds)}] Using existing code: {code_path}")
            #     code = code_path.read_text(encoding="utf-8")
            if 1 == 0:
                pass
            else:
                print(f"[{i+1}/{len(ds)}] Generating code for: {code_path}")
                response, code_obj = llm.get_json_response_retry(msg_list, SchematicEditCode)

                if code_obj is None or not code_obj.code:
                    rec = {
                        "test_idx": i,
                        "module_name": module_name,
                        "schematic_name": schematic_name,
                        "passed": 0,
                        "errors": ev.get("errors", None),
                        "netlist_evaluation": ev.get("netlist_evaluation", None),
                        "exception": ev.get("exception", None),
                    }

                    _append_jsonl(out_jsonl, rec)
                    csv_writer.writerow(rec)
                    csv_fh.flush()
                    done_pairs.add(key)
                    continue
                else:
                    code = code_obj.code.replace("\\\"", "\"").replace("\\n", "\n")
                code_path.parent.mkdir(parents=True, exist_ok=True)
                code = _sanitize_and_validate_code(code)
                code = get_final_python(code, out_path=code_path)

            try:
                ev = evaluation(line, code_path, code)
                ev = ev if isinstance(ev, dict) else {"passed": 0}
            except Exception as e:
                print("ERROR:", e)
                ev = {"passed": 0, "netlist_evaluation": None, "errors": None, "exception": str(e)}

            passed_flag = int(bool(ev.get("passed", 0)))
            if passed_flag == 0:
                rec = {
                    "test_idx": i,                 # Sampling order from 1..k
                    "module_name": module_name,
                    "schematic_name": schematic_name,
                    "passed": passed_flag,
                    "errors": ev.get("errors", None),
                    "netlist_evaluation": ev.get("netlist_evaluation", None),
                    "exception": ev.get("exception", None),
                }
            else:
                passed_cnt += passed_flag
                if isinstance(ev.get("errors", 0), int):
                    total_errors += ev["errors"]

                rec = {
                    "test_idx": i,
                    "module_name": module_name,
                    "schematic_name": schematic_name,
                    "passed": passed_flag,
                    "errors": ev.get("errors", None),
                    "netlist_evaluation": ev.get("netlist_evaluation", None),
                    "exception": ev.get("exception", None),
                }

            _append_jsonl(out_jsonl, rec)
            csv_writer.writerow(rec)
            csv_fh.flush()
            done_pairs.add(key)

        print(f"  Seen:   {total_seen}")
        print(f"  Passed: {passed_cnt}/{total_seen}  ({(passed_cnt / max(1,total_seen)):.1%})")
        print(f"  Sum(errors): {total_errors}")
        print(f"  Results JSONL: {out_jsonl}")
        print(f"  Results CSV  : {out_csv}")

        return {
            "passed": passed_cnt,
            "sum_errors": total_errors,
            "out_jsonl": str(out_jsonl),
            "out_csv": str(out_csv),
        }

    finally:
        try:
            csv_fh.close()
        except Exception:
            pass


if __name__ == "__main__":
    eval_path = Path(project_path) / "gptoss_training" / "novel_eval_runs"
    for i in range(len(model_names)):
        for level in levels:
            run_batch_evaluation(jsonl_path = str(Path(project_path) / "jsonl_dataset" / "new_form" / f"finetune_dataset_sch_int_rl_medium_novel.jsonl"), out_dir=eval_path, model_name=model_names[i], level=level)