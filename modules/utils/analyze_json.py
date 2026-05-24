#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Execute Python code embedded in a dataset record and extract meta fields.

Features:
- Load a JSON record
- Extract the last assistant message's 'content' as Python code.
- Execute the code in a fresh global namespace.
- Print module_name and schematic_name parsed from meta:
  * module_name: meta['module_name'] or meta['module']
  * schematic_name: meta['schematic_name'] or meta['schematic']

Usage:
  python run_record.py --input record.json --project-path /your/project/root
  # or pipe from stdin:
  cat record.json | python run_record.py

Notes:
- If your code expects environment variable PROJECT_PATH, pass --project-path
  or ensure it is already set in the environment.
"""

import sys
import os
import json
import argparse
import traceback
from pathlib import Path
from typing import Tuple, Dict, Any

def load_json_text(input_arg: str | None) -> str:
    """Load JSON string from a file path or stdin if input_arg is None or '-'."""
    if input_arg and input_arg != "-":
        return Path(input_arg).read_text(encoding="utf-8")
    return sys.stdin.read()

def extract_code(record: Dict[str, Any]) -> str:
    """Get Python code from the last assistant message's 'content' field."""
    messages = record.get("messages", [])
    assistants = [m for m in messages if m.get("role") == "assistant"]
    if not assistants:
        raise ValueError("No assistant messages found in 'messages'.")
    code = assistants[-1].get("content", "")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Assistant 'content' is empty or not a string.")
    return code

def extract_meta_info(record: Dict[str, Any]) -> Tuple[str | None, str | None, Dict[str, Any]]:
    """Extract module_name and schematic_name with fallbacks, and return meta."""
    meta = record.get("meta", {}) or {}
    module_name = meta.get("module_name") or meta.get("module")
    schematic_name = meta.get("schematic_name") or meta.get("schematic")
    return module_name, schematic_name, meta

def write_code(code: str, code_path: str) -> str | None:
    """If meta['code_path'] exists, write code to that path and return it."""
    if code_path:
        p = Path(code_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")