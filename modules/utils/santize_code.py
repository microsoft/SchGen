import io
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict
from contextlib import redirect_stdout, redirect_stderr


def _dedupe_keywords_in_calls(code: str, func_names: list[str]) -> str:
    """
    Dedupe repeated keyword args inside calls to specified functions.
    Keeps the LAST occurrence of the same keyword.

    This is a best-effort text fix meant for model-generated code.
    It handles common cases like:
        add_label(a=1, a=2, b=3)
    and tries to not break nested parentheses by using a small parser.
    """

    def find_calls(src: str, fname: str):
        # Return list of (start_idx, end_idx, inside_args_string)
        hits = []
        pat = re.compile(rf"\b{re.escape(fname)}\s*\(")
        for m in pat.finditer(src):
            start = m.start()
            i = m.end()  # position after '('
            depth = 1
            in_str = None
            esc = False
            while i < len(src) and depth > 0:
                ch = src[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == in_str:
                        in_str = None
                else:
                    if ch in ("'", '"'):
                        in_str = ch
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                i += 1
            if depth == 0:
                end = i  # index right after ')'
                inside = src[m.end(): end - 1]
                hits.append((start, end, inside))
        return hits

    def split_top_level_args(arg_str: str) -> list[str]:
        args = []
        cur = []
        depth = 0
        in_str = None
        esc = False
        for ch in arg_str:
            if in_str:
                cur.append(ch)
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == in_str:
                    in_str = None
                continue

            if ch in ("'", '"'):
                in_str = ch
                cur.append(ch)
            elif ch in "([{":
                depth += 1
                cur.append(ch)
            elif ch in ")]}":
                depth -= 1
                cur.append(ch)
            elif ch == "," and depth == 0:
                s = "".join(cur).strip()
                if s:
                    args.append(s)
                cur = []
            else:
                cur.append(ch)

        tail = "".join(cur).strip()
        if tail:
            args.append(tail)
        return args

    def dedupe_arglist(arglist: str) -> str:
        parts = split_top_level_args(arglist)
        # Keep positional args in order; dedupe kwargs by key (keep last).
        positional = []
        kw_positions = []  # keep original order of first appearance for stable output
        kw_map: dict[str, str] = {}

        for p in parts:
            # detect kwarg: top-level "name = value"
            # (we only treat it as kwarg if '=' exists and left side looks like identifier)
            eq = p.find("=")
            if eq == -1:
                positional.append(p)
                continue
            key = p[:eq].strip()
            val = p[eq + 1:].strip()
            if re.fullmatch(r"[A-Za-z_]\w*", key):
                if key not in kw_map:
                    kw_positions.append(key)
                kw_map[key] = val  # overwrite => keep last
            else:
                # weird expression with '=' (rare), keep as positional-ish
                positional.append(p)

        rebuilt = []
        rebuilt.extend(positional)
        # To keep "last wins" AND preserve reasonable ordering, emit kwargs in order of first appearance
        for k in kw_positions:
            rebuilt.append(f"{k}={kw_map[k]}")
        return ", ".join(rebuilt)

    out = code
    # Apply per function, from end to start to preserve indices
    for fname in func_names:
        calls = find_calls(out, fname)
        if not calls:
            continue
        new_out = out
        for (start, end, inside) in reversed(calls):
            fixed_inside = dedupe_arglist(inside)
            new_out = new_out[:start] + f"{fname}({fixed_inside})" + new_out[end:]
        out = new_out

    return out


def sanitize_generated_code(code: str) -> str:
    """
    Best-effort sanitizer for LLM-generated Python code before compile().
    Extend this over time as you observe more syntax issues.
    """
    # Fix repeated keyword args in calls that are known to appear.
    code = _dedupe_keywords_in_calls(code, func_names=[
        "add_label",
        # "add_global_label",
        # "add_schematic_symbol",
        # "connect_pin_to_label",
    ])
    return code