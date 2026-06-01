# Load the model
import torch
from transformers import AutoModelForCausalLM, Mxfp4Config
from transformers import AutoTokenizer
from pathlib import Path
import sys
import os
project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)
import re
from typing import Union
import argparse




def save_final_python(decoded: str, out_path: Union[str, Path] = "generated.py") -> Path:
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
    code_text = code_fence_re.sub("", segment).strip()

    # 4) Write to file
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(code_text, encoding="utf-8")

    return out_path

# Get tokenizer
tokenizer = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")

# # Save current chat template as a temp file to check its content.
# temp_chat_template_path = Path(project_path) / "temp_chat_template.txt"
# with temp_chat_template_path.open("w", encoding="utf-8") as f:
#     f.write(tokenizer.chat_template if tokenizer.chat_template is not None else "")

# load a modified chat template from a file ({% generation %} and {% endgeneration %} addded for assistant_only_loss)
# Reasoning effort set to be high
new_chat_template_path = Path(project_path) / "training" / "modified_chat_template.txt"
with new_chat_template_path.open("r", encoding="utf-8") as f:
    new_chat_template = f.read()

tokenizer.chat_template = new_chat_template

# Configure quantization and model parameters
quantization_config = Mxfp4Config(dequantize=True)
model_kwargs = dict(
    attn_implementation="flash_attention_2",
    torch_dtype=torch.bfloat16,
    quantization_config=quantization_config,
    use_cache=False,
)

# Get the model
model = AutoModelForCausalLM.from_pretrained("openai/gpt-oss-20b", **model_kwargs)

# Reset special tokens

model.config.pad_token_id = tokenizer.pad_token_id
model.config.bos_token_id = tokenizer.bos_token_id
model.config.eos_token_id = tokenizer.eos_token_id

model.generation_config.pad_token_id = tokenizer.pad_token_id
model.generation_config.bos_token_id = tokenizer.bos_token_id
model.generation_config.eos_token_id = tokenizer.eos_token_id

# Test base model

# editor = SchematicEditor(model="o4")
# editor.sch_request = "I want a small LED circuit driven by 3.3V power, please give me the code that generates it."
# editor.img_ref_path = None # Avoid trigger error

# msg_list = prepare_context()
# symbol_context = editor.prepare_symbol_context()

# msg_list.append({"role": "user", 
#                 "content": f"""
#                 The user request is: {editor.sch_request}
#                 ###
#                     We have the following symbols and their related context information as listed below: {symbol_context}
#                 ###
#                 """})


# # Apply Chat template
# input_ids = tokenizer.apply_chat_template(
#     msg_list,
#     add_generation_prompt=True,
#     return_tensors="pt",
# ).to(model.device)

# # Test with base model
# output_ids = model.generate(input_ids, max_new_tokens=2048)
# response = tokenizer.batch_decode(output_ids)[0]

# path = save_final_python(response, out_path="generated.py")
# print(response)
# print(f"Saved generated code to {path}")

# Configuration of LoRa
from peft import LoraConfig, get_peft_model

peft_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules="all-linear",
    target_parameters=[
        # "3.mlp.experts.gate_up_proj",
        # "3.mlp.experts.down_proj",
        "7.mlp.experts.gate_up_proj",
        "7.mlp.experts.down_proj",
        # "11.mlp.experts.gate_up_proj",
        # "11.mlp.experts.down_proj",
        "15.mlp.experts.gate_up_proj",
        "15.mlp.experts.down_proj",
        # "19.mlp.experts.gate_up_proj",
        # "19.mlp.experts.down_proj",
        "23.mlp.experts.gate_up_proj",
        "23.mlp.experts.down_proj",
    ],
)
peft_model = get_peft_model(model, peft_config)
peft_model.print_trainable_parameters()

# Configuration of supervised finetuning
from trl import SFTConfig

MAX_TOKENS = 13312


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the schematic finetuning model.")
    parser.add_argument(
        "--out_dir",
        type=str,
        help="Directory to save the trained model.",
    )
    parser.add_argument(
        "--data_file",
        type=str,
        help="Path to the training JSONL dataset.",
    )
    return parser


args = build_parser().parse_args()
OUT_DIR = args.out_dir

training_args = SFTConfig(
    learning_rate=4e-4,
    gradient_checkpointing=True,
    num_train_epochs=2,
    logging_steps=1,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    assistant_only_loss=True,
    max_length=MAX_TOKENS,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine_with_min_lr",
    lr_scheduler_kwargs={"min_lr_rate": 0.1},
    output_dir=OUT_DIR,
    # eval_strategy="steps",     
    # eval_steps=100, 
    # load_best_model_at_end=True,
    # metric_for_best_model="eval_loss",
    # greater_is_better=False,
    save_strategy="epoch",
    report_to=["trackio"],
    push_to_hub=False,
)

# Training
from trl import SFTTrainer
from datasets import load_dataset
DATA_FILE = Path(args.data_file)

raw = load_dataset("json", data_files={"train": str(DATA_FILE)})["train"]

def len_ok(example):
    # Render + tokenize exactly like training
    ids = tokenizer.apply_chat_template(
        example["messages"],
        add_generation_prompt=False, 
        tokenize=True
    )
    return len(ids) < MAX_TOKENS

filtered = raw.filter(len_ok, num_proc=4, desc="Filtering by length")

print(f"kept {len(filtered)} / {len(raw)} samples (< {MAX_TOKENS} tokens)")

trainer = SFTTrainer(
    model=peft_model,
    args=training_args,
    train_dataset=filtered,
    processing_class=tokenizer,
)

trainer.train()

# Save the trained model and upload it to HuggingFace
trainer.save_model(OUT_DIR)
# trainer.push_to_hub(dataset_name=f"HuggingFaceH4/{OUT_DIR}")