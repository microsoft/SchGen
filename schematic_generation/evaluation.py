## Evaluate different models on a common test set

import torch
from pathlib import Path
import sys
import os
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)
import re
from typing import Union
from datasets import load_dataset
import random
import json
import csv
import tqdm
from datetime import datetime
import pandas as pd
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
model_names = ["gpt-oss-20b-pcb-finetune_L1_int_rl_medium"] # ["gpt-oss-20b-pcb-finetune_L1_int_design_level", "gpt-oss-20b-pcb-finetune_L1_int_rl_medium"]
RANDOM_SAMPLING = True

def get_final_python(decoded: str) -> Path:
    """
    Extract the 'final' section from a decoded model output, strip trailing

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
    code_text = code_fence_re.sub("", segment).strip()

    return code_text


# Load trained model
from transformers import AutoModelForCausalLM, AutoTokenizer, Mxfp4Config
from peft import PeftModel

# Load the tokenizer
tokenizer = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")

reasoning_level = "medium"

if reasoning_level == "high":
    new_chat_template_path = Path(project_path) / "training" / "modified_chat_template_rl_high.txt"
else:
    new_chat_template_path = Path(project_path) / "training" / "modified_chat_template.txt"


with new_chat_template_path.open("r", encoding="utf-8") as f:
    new_chat_template = f.read()

@torch.no_grad()
def build_inputs_and_labels_content_only(messages, tokenizer, device, max_eval_tokens=4096):
    """
    Build input_ids / labels for validation loss.
    Only the LAST assistant.content contributes to the loss.
    assistant.thinking is included as context but masked out.
    Optionally truncate to the last max_eval_tokens tokens to avoid OOM.
    """

    # Find the last assistant message 
    last_assistant_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "assistant":
            last_assistant_idx = i
            break

    if last_assistant_idx is None:
        raise ValueError("No assistant message found in messages.")

    target_msg = messages[last_assistant_idx]
    prefix_msgs = messages[:last_assistant_idx]

    thinking = target_msg.get("thinking", "")
    content = target_msg.get("content", "")

    # 1) Prefix + assistant(thinking only, content masked out)
    msg_thinking_only = {
        "role": "assistant",
        "thinking": thinking,
        "content": "",
    }
    ids_before_content = tokenizer.apply_chat_template(
        prefix_msgs + [msg_thinking_only],
        tokenize=True,
        add_generation_prompt=False,
    )

    # 2) Prefix + assistant(thinking + content) -> only this part contributes to loss
    msg_full = {
        "role": "assistant",
        "thinking": thinking,
        "content": content,
    }
    ids_after_content = tokenizer.apply_chat_template(
        prefix_msgs + [msg_full],
        tokenize=True,
        add_generation_prompt=False,
    )

    full_ids = ids_after_content
    labels = [-100] * len(full_ids)

    start = len(ids_before_content)
    end = len(ids_after_content)
    labels[start:end] = full_ids[start:end]

    # Only keep the last max_eval_tokens tokens to avoid OOM, if specified
    if max_eval_tokens is not None and len(full_ids) > max_eval_tokens:
        full_ids = full_ids[-max_eval_tokens:]
        labels = labels[-max_eval_tokens:]

    input_ids = torch.tensor([full_ids], dtype=torch.long, device=device)
    labels = torch.tensor([labels], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(input_ids, device=device)

    return input_ids, attention_mask, labels

@torch.no_grad()
def compute_validation_loss_content_only(messages, model, tokenizer):
    input_ids, attention_mask, labels = build_inputs_and_labels_content_only(
        messages=messages,
        tokenizer=tokenizer,
        device=model.device,
    )

    # Sanity Check: Print content (ground truth) that used to calculate loss, and number of tokens contributing to loss
    # num_loss_tokens = (labels != -100).sum().item()
    # print("num_loss_tokens =", num_loss_tokens)

    # active_positions = (labels[0] != -100).nonzero(as_tuple=True)[0]
    # if len(active_positions) > 0:
    #     s = active_positions[0].item()
    #     e = active_positions[-1].item() + 1
    #     print(tokenizer.decode(input_ids[0][s:e]))

    outputs = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels,
    )

    # Release GPU memory immediately after loss computation
    del input_ids, attention_mask, labels
    torch.cuda.empty_cache()

    return float(outputs.loss.item())

tokenizer.chat_template = new_chat_template

def save_jsonl(path: str, items):
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

def run_batch_evaluation(
    jsonl_path: str,
    out_dir: str = "eval_runs",
    model_name: str = None,
):

    # Load the original model first
    quantization_config = Mxfp4Config(dequantize=True)
    model_kwargs = dict(attn_implementation="flash_attention_2", torch_dtype=torch.bfloat16, use_cache=False, device_map="auto", quantization_config=quantization_config)
    base_model = AutoModelForCausalLM.from_pretrained("openai/gpt-oss-20b", **model_kwargs)
    # Merge fine-tuned weights with the base model
    if model_name == None:
        model.eval()
    else:
        peft_model_id = Path(project_path) / "models" / model_name
        model = PeftModel.from_pretrained(base_model, peft_model_id)
        model = model.merge_and_unload()
        model.eval()

    CODE_PATH = Path(project_path) / "export" / f"test_code_{model_name}"

    Path(CODE_PATH).mkdir(parents=True, exist_ok=True)

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
    # Santize model name for file naming
    model_name_sanitized = model_name.replace("/", "_").replace("\\", "_")

    out_jsonl = os.path.join(out_dir, f"eval_results_seed_{model_name_sanitized}.jsonl")
    out_csv   = os.path.join(out_dir, f"eval_results_seed_{model_name_sanitized}.csv")

    ds = load_dataset("json", data_files=jsonl_path, split="train")
    results = []
    passed_cnt = 0
    total_errors = 0

    csv_path = Path(out_csv)
    existing_records = {}

    # Read existing CSV if exists to allow resuming and skipping already passed cases, and reusing val_loss without recomputation
    if csv_path.exists():
        old_df = pd.read_csv(csv_path)
        if "test_idx" in old_df.columns:
            for _, row in old_df.iterrows():
                test_idx = int(row["test_idx"])
                existing_records[test_idx] = row.to_dict()

    results = []

    for i in tqdm.tqdm(range(100), desc=f"Evaluating {model_name}"):

        module_name, schematic_name, meta = extract_meta_info(ds[i])
        style = meta.get("style")
        thinking_model = meta.get("thinking_model")
        line = ds[i]
        all_messages = ds[i]["messages"]  # full conversation
        msg_list = all_messages[:2]       # system + user

        # old_rec = existing_records.get(i)

        # -------------------------
        # 1. if old record exists and is passed, skip evaluation and reuse old record (including val_loss if exists)
        # -------------------------
        # if old_rec is not None:
        #     old_passed = old_rec.get("passed", 0)
        #     try:
        #         old_passed = int(old_passed)
        #     except Exception:
        #         old_passed = 0

        #     if old_passed == 1:
        #         print(f"[{i+1}/{len(ds)}] Skipping existing passed record: test_idx={i}")
        #         results.append(old_rec)
        #         passed_cnt += 1

        #         old_errors = old_rec.get("errors", None)
        #         if pd.notna(old_errors):
        #             try:
        #                 total_errors += int(old_errors)
        #             except Exception:
        #                 pass
        #         continue

        # -------------------------
        # 2. val_loss:
        #    - if old record has val_loss, reuse it to avoid expensive recomputation
        #    - if no old record or val_loss, compute it and save in the new record (will be reused in future if needed)
        # -------------------------
        val_loss = None
        # if old_rec is not None and "val_loss" in old_rec and pd.notna(old_rec["val_loss"]):
        #     val_loss = float(old_rec["val_loss"])
        # else:
        #     val_loss = compute_validation_loss_content_only(
        #         messages=all_messages,
        #         model=model,
        #         tokenizer=tokenizer,
        #     )

        code_path = Path(CODE_PATH) / f"{module_name}_{schematic_name}_{thinking_model}_{style}_test.py"

        # -------------------------
        # 3. Generate code with the model, but if the code file already exists (from previous run), reuse it to save time and GPU resources. This allows iterative improvement and debugging without regenerating code for already working cases.
        # -------------------------
        if code_path.exists():
            print(f"[{i+1}/{len(ds)}] Reusing existing code: {code_path}")
            code = code_path.read_text(encoding="utf-8")
        else:
            input_ids = tokenizer.apply_chat_template(
                msg_list,
                add_generation_prompt=True,
                return_tensors="pt",
            ).to(model.device)

            output_ids = model.generate(
                input_ids,
                max_new_tokens=MAX_TOKENS,
                attention_mask=torch.ones_like(input_ids),
            )

            gen_only = output_ids[:, input_ids.shape[-1]:]
            response = tokenizer.batch_decode(gen_only, skip_special_tokens=False)[0]
            code = get_final_python(response)

            code_path.parent.mkdir(parents=True, exist_ok=True)
            code_path.write_text(code, encoding="utf-8")

            del input_ids, output_ids, gen_only
            torch.cuda.empty_cache()

        # -------------------------
        # 4. Run evaluation
        # -------------------------
        try:
            ev = evaluation(line, code_path, code)
            ev = ev if isinstance(ev, dict) else {"passed": 0}
            print(f"[{i+1}/{len(ds)}] Evaluation result: {ev}")
        except Exception as e:
            print("ERROR:", e)
            ev = {
                "passed": 0,
                "netlist_evaluation": None,
                "errors": None,
                "exception": str(e),
            }

        passed_cnt += int(bool(ev.get("passed", 0)))

        errors_val = ev.get("errors", None)
        if isinstance(errors_val, int):
            total_errors += errors_val

        # -------------------------
        # 5. new record should overwrite old record if exists, to update with new evaluation results and reuse val_loss if it was already computed before
        # -------------------------
        rec = {
            "test_idx": i,
            "module_name": module_name,
            "schematic_name": schematic_name,
            "passed": int(bool(ev.get("passed", 0))),
            "errors": ev.get("errors", None),
            "erc_errors": ev.get("erc_errors", None),
            "netlist_evaluation": ev.get("netlist_evaluation", None),
            "val_loss": val_loss,
            "style": style,
        }
        results.append(rec)

    new_df = pd.DataFrame(results)

    if csv_path.exists():
        old_df = pd.read_csv(csv_path)
        # Merge old and new records, giving priority to new records (keep="last") in case of duplicate test_idx, then sort by test_idx
        merged_df = pd.concat([old_df, new_df], ignore_index=True)
        merged_df = merged_df.drop_duplicates(subset=["test_idx"], keep="last")
    else:
        merged_df = new_df

    merged_df = merged_df.sort_values("test_idx").reset_index(drop=True)
    merged_df.to_csv(csv_path, index=False)

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
        "results": results,
    }


if __name__ == "__main__":
    
    eval_path = Path(project_path) / "gptoss_training" / "new_eval_runs"
    for i in range(len(model_names)):
        run_batch_evaluation(jsonl_path = str(Path(project_path) / "jsonl_dataset" / "old_form" / "finetune_dataset_L1_int.test.jsonl"), out_dir=eval_path, model_name=model_names[i])