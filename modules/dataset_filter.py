dataset = "finetune_dataset.jsonl"

import json
import os
from pathlib import Path
from typing import Union, Optional
import re

# Match any <|channel|>X<|message|> ... (until next channel/end/EOS)
_SEG_RE = re.compile(
    r"<\|channel\|>\s*(\w+)\s*<\|message\|>(.*?)\s*(?=(?:<\|channel\|>|<\|end\|>|$))",
    re.S | re.I
)

# Optional suffix like <|return|> (may repeat)
_RETURN_SUFFIX_RE = re.compile(r"(?:\s*<\|return\|>\s*)+$", re.S)

# Optional markdown code fence cleanup
_CODE_FENCE_RE = re.compile(r"^\s*```(?:[Pp]ython)?\s*\n|\n\s*```\s*$", re.S)

def extract_final(text: Optional[str]) -> str:
    """
    Extract the FINAL message payload from a model-formatted string.

    Rules:
    1) If a <|channel|>final<|message|>...</|end|> segment exists, return its content.
    2) Otherwise, return the content of the last <|message|> segment.
    3) Do NOT assume the output ends with <|return|>; strip it only when present.
    4) Remove surrounding markdown code fences if the model wrapped the code.

    Parameters
    ----------
    text : str | None
        Full decoded string (do NOT pre-strip special tokens).

    Returns
    -------
    str
        Cleaned final content.
    """
    if not text:
        return ""

    # Find all channel/message segments
    segs = list(_SEG_RE.finditer(text))

    # Prefer explicit 'final' segment; otherwise fall back to last segment
    chosen = None
    for m in segs:
        if m.group(1).lower() == "final":
            chosen = m
    if chosen is None and segs:
        chosen = segs[-1]

    # If no segments found at all, return the raw text (trimmed)
    if chosen is None:
        payload = text.strip()
    else:
        payload = chosen.group(2).strip()

    # Strip trailing <|return|> if present (but do not require it)
    payload = _RETURN_SUFFIX_RE.sub("", payload).strip()

    # Optionally remove markdown code fences
    payload = _CODE_FENCE_RE.sub("", payload).strip()

    return payload

def get_thinking(obj: dict) -> str | None:
    # 2) fallback: last assistant message's thinking
    for m in reversed(obj.get("messages", [])):
        if m.get("role") == "assistant":
            th = m.get("thinking")
            if isinstance(th, str) and th.strip():
                return th.strip()
    return None

def normalize_jsonl_thinking_to_final(jsonl_path: Union[str, Path], inplace: bool = True, out_path: Union[str, Path] = None) -> Path:
    """
    For each line in a JSONL file, check the `thinking` field. If it contains
    channel tags (e.g., <|channel|>, <|message|>, <|end|>, <|return|>), extract
    the FINAL segment by calling `extract_final(thinking)` and store it back
    into `thinking`.

    Parameters
    ----------
    jsonl_path : str | Path
        Path to the input .jsonl file.
    inplace : bool, default True
        If True, replace the original file atomically. If False, write to out_path.
    out_path : str | Path, optional
        Destination .jsonl path when inplace=False. If not provided, a `.fixed.jsonl`
        sibling will be created.

    Returns
    -------
    Path
        The path to the written JSONL file.
    """
    jsonl_path = Path(jsonl_path)

    # Decide output target
    if inplace:
        tmp_path = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
        target_path = jsonl_path
    else:
        if out_path is None:
            out_path = jsonl_path.with_suffix(".fixed.jsonl")
        tmp_path = Path(out_path)
        target_path = Path(out_path)

    fixed, total = 0, 0

    with jsonl_path.open("r", encoding="utf-8") as fin, tmp_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            total += 1
            raw = line.rstrip("\n")
            if not raw.strip():
                fout.write(line)
                continue

            try:
                obj = json.loads(raw)
            except Exception:
                # If the line is not valid JSON, keep it as-is
                fout.write(line)
                continue

            updated = False
            msgs = obj.get("messages") or []
            # Find the last assistant message
            for m in reversed(msgs):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    # Prefer existing assistant.thinking; fallback to assistant.content
                    src = m.get("thinking")
                    if not (isinstance(src, str) and src.strip()):
                        src = m.get("content", "")
                    new_th = extract_final(src)

                    # Only write back if changed and non-empty
                    if isinstance(new_th, str) and new_th and new_th != m.get("thinking"):
                        m["thinking"] = new_th
                        updated = True
                    break  # stop after updating the last assistant

            if updated:
                fixed += 1

            # Write back the (possibly modified) object
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Atomic replace if inplace
    if inplace:
        os.replace(tmp_path, target_path)

    print(f"[DONE] processed={total}, rewritten_thinking={fixed}, output={target_path}")
    return target_path


normalize_jsonl_thinking_to_final(dataset, inplace=True)