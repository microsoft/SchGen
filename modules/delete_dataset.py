#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trim system message content after a specific starting phrase.

Usage:
  python trim_system.py --in data.json --out cleaned.json
  python trim_system.py --in data.jsonl --out cleaned.jsonl --jsonl
  # or stream:
  cat data.jsonl | python trim_system.py --jsonl > cleaned.jsonl
"""

import argparse, json, sys
from typing import Any, Iterable

START_PHRASE = (
    "Below is an example of KiCAD schematic file of a IMU module with the chip of ICM-20948 as U2, "
    "one 1.8v rail, 4 gnd rails, 3 capacitors with C1: 1.0 uF, C2: 0.1 uF, C3: 0.1 uF and 6 labels. "
    "U2 pin 1 is connected to the 1.8V rail, C1 pin 1, C2 pin 1, C3 pin 1, U2 pin 3 is connected to label INT,"
)

def load_items(path: str, jsonl: bool) -> Iterable[Any]:
    fh = sys.stdin if path == "-" else open(path, "r", encoding="utf-8")
    with fh:
        if jsonl:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
        else:
            data = json.load(fh)
            if isinstance(data, list):
                for x in data: yield x
            else:
                # single object
                yield data

def dump_items(items: Iterable[Any], path: str, jsonl: bool):
    fh = sys.stdout if path == "-" else open(path, "w", encoding="utf-8")
    with fh:
        if jsonl:
            for obj in items:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        else:
            objs = list(items)
            json.dump(objs if len(objs) != 1 else objs[0], fh, ensure_ascii=False, indent=2)

def trim_system_message(obj: Any) -> Any:
    """
    If obj has a 'messages' list, find entries where role == 'system' and
    cut content from START_PHRASE to the end (inclusive).
    """
    if not isinstance(obj, dict):
        return obj

    msgs = obj.get("messages")
    if not isinstance(msgs, list):
        return obj

    changed = 0
    for m in msgs:
        if isinstance(m, dict) and m.get("role") == "system":
            content = m.get("content")
            if isinstance(content, str):
                idx = content.find(START_PHRASE)
                if idx >= 0:
                    m["content"] = content[:idx].rstrip()
                    changed += 1
    obj["_trim_system_applied"] = changed  # optional: for auditing; remove if not needed
    return obj

def main():
    ap = argparse.ArgumentParser(description="Trim system message content from a start phrase to the end.")
    ap.add_argument("--in", dest="inp", default="finetune_dataset_raw.jsonl", help="Input file path (json or jsonl). '-' for stdin.")
    ap.add_argument("--out", dest="out", default="finetune_dataset_cleaned.jsonl", help="Output file path. '-' for stdout.")
    ap.add_argument("--jsonl", action="store_true", help="Treat input/output as JSONL.")
    args = ap.parse_args()

    cleaned = (trim_system_message(item) for item in load_items(args.inp, args.jsonl))
    dump_items(cleaned, args.out, args.jsonl)

if __name__ == "__main__":
    main()
