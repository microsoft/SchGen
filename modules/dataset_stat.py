#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute reference-free intrinsic metrics per representation file:
- Pseudo-Perplexity (masked LM)
- Compression (gzip BPB, bits per event)
- LZ76 normalized complexity
- AST/schema parseability metrics
- Type-specific health metrics (pins/wires/base)

Usage:
  pip install transformers torch bert-score zstandard tqdm
  python intrinsic_metrics.py --project-path "$PROJECT_PATH" --dataset-rel dataset --out intrinsic_metrics.csv
"""

from __future__ import annotations
import os, re, io, math, json, gzip, bz2, argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from tqdm import tqdm

# ---------- Canonicalization (same spirit as before, simplified) ----------
import ast

NUM_PREC = 3
FUNC_ALIAS = {
    "add_new_wire": "wire",
    "add_schematic_symbol": "symbol",
    "add_schematic_symbol": "symbol",
    "connect_pins": "pinlink",
    "get_pin_location": "getpin",
}

def _is_simple(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant): return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)): return all(_is_simple(e) for e in node.elts)
    if isinstance(node, ast.Dict): return all(_is_simple(k) and _is_simple(v) for k,v in zip(node.keys,node.values))
    return False

def _norm(v: Any) -> Any:
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v): return str(v)
        x = round(v, NUM_PREC); return 0.0 if x == 0 else x
    if v is None: return "none"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, (list, tuple, set)): return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(vv) for k, vv in sorted(((str(k), vv) for k,vv in v.items()), key=lambda x: x[0])}
    return v

def _name_of(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name): return f.id
    if isinstance(f, ast.Attribute):
        parts = []
        cur = f
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name): parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    return "<other>"

@dataclass
class Canon:
    text: str
    stats: Dict[str, Any]

def canonicalize_py(path: Path) -> Canon:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    calls, lits = [], []
    stats = dict(total_calls=0, recognized_calls=0, total_args=0, literal_args=0, nonliteral_args=0)
    try:
        tree = ast.parse(raw, filename=str(path))
    except Exception:
        # fallback: keep non-empty non-comment lines
        clean = "\n".join(l for l in (ln.strip() for ln in raw.splitlines()) if l and not l.startswith("#"))
        return Canon(text=clean, stats={"parse_error": True, **stats})

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            fname = _name_of(node)
            fname_alias = FUNC_ALIAS.get(fname, fname)
            parts = [f"CALL {fname_alias}"]
            stats["total_calls"] += 1
            if fname_alias in {"wire","symbol","pinlink","getpin"}:
                stats["recognized_calls"] += 1
            # positional
            for i,a in enumerate(node.args):
                stats["total_args"] += 1
                if _is_simple(a):
                    stats["literal_args"] += 1
                    val = norm_ast(a)
                else:
                    stats["nonliteral_args"] += 1
                    val = f"<expr:{type(a).__name__}>"
                parts.append(f"arg{i}={json.dumps(val, ensure_ascii=False, sort_keys=True)}")
            # keywords
            kws = []
            for kw in node.keywords:
                k = kw.arg if kw.arg is not None else "<**>"
                stats["total_args"] += 1
                if _is_simple(kw.value):
                    stats["literal_args"] += 1
                    val = norm_ast(kw.value)
                else:
                    stats["nonliteral_args"] += 1
                    val = f"<expr:{type(kw.value).__name__}>"
                kws.append((k, val))
            for k,v in sorted(kws, key=lambda x: x[0]):
                parts.append(f"kw:{k}={json.dumps(v, ensure_ascii=False, sort_keys=True)}")
            calls.append(" ".join(parts))
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign):
            if _is_simple(node.value):
                lits.append(f"LIT {json.dumps(norm_ast(node.value), ensure_ascii=False, sort_keys=True)}")
            self.generic_visit(node)

    def norm_ast(n: ast.AST) -> Any:
        if isinstance(n, ast.Constant): return _norm(n.value)
        if isinstance(n, ast.Num): return _norm(n.n)       # <3.8
        if isinstance(n, ast.Str): return _norm(n.s)
        if isinstance(n, ast.NameConstant): return _norm(n.value)
        if isinstance(n, (ast.Tuple,ast.List,ast.Set)): return _norm([norm_ast(e) for e in n.elts])
        if isinstance(n, ast.Dict):
            pairs = sorted(((str(norm_ast(k)), norm_ast(v)) for k,v in zip(n.keys,n.values)), key=lambda x: x[0])
            return _norm({k:v for k,v in pairs})
        return f"<nonliteral:{type(n).__name__}>"

    V().visit(tree)
    lines = sorted(set(calls + lits))
    text = "\n".join(lines)
    # derived parseability
    tot_args = max(1, stats["total_args"])
    stats.update(
        parse_error=False,
        recognized_call_ratio= (stats["recognized_calls"]/max(1,stats["total_calls"])),
        literal_arg_ratio= (stats["literal_args"]/tot_args),
        nonliteral_arg_rate= (stats["nonliteral_args"]/tot_args),
        events=len(lines),
        raw_bytes=len(text.encode("utf-8")),
    )
    return Canon(text=text, stats=stats)

# ---------- Compression & LZ complexity ----------
def gzip_bpb(s: str) -> float:
    raw = s.encode("utf-8")
    if not raw: return 0.0
    comp = gzip.compress(raw, compresslevel=9)
    return (8.0*len(comp))/len(raw)

def zstd_bpb(s: str) -> Optional[float]:
    try:
        import zstandard as zstd
    except Exception:
        return None
    raw = s.encode("utf-8")
    if not raw: return 0.0
    cctx = zstd.ZstdCompressor(level=19)
    comp = cctx.compress(raw)
    return (8.0*len(comp))/len(raw)

def lz76_norm(s: str) -> float:
    """Simple LZ76 phrase count normalization on bytes."""
    b = s.encode("utf-8")
    n = len(b)
    if n == 0: return 0.0
    i, c, d = 0, 0, 1
    while i + d <= n:
        if b[i:i+d] in b[0:i]:
            d += 1
            if i + d - 1 > n: break
        else:
            c += 1
            i = i + d
            d = 1
    # normalized complexity
    return (c*math.log(max(2,n), 2))/n

# ---------- Pseudo-PPL with masked LM ----------
import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM

class PseudoPPL:
    def __init__(self, model_name="microsoft/codebert-base", device=None, max_len=512, subsample=256):
        self.tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        self.model = AutoModelForMaskedLM.from_pretrained(model_name)
        self.model.eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.max_len = max_len
        self.subsample = subsample

    @torch.no_grad()
    def ppl(self, text: str) -> float:
        if not text.strip(): return 0.0
        toks = self.tok(text, return_tensors="pt", truncation=True, max_length=self.max_len)
        input_ids = toks["input_ids"][0]
        attn = toks["attention_mask"][0]
        # choose token positions to score (exclude special tokens)
        idxs = [i for i,t in enumerate(input_ids.tolist()) if t not in (self.tok.cls_token_id, self.tok.sep_token_id, self.tok.bos_token_id, self.tok.eos_token_id)]
        if self.subsample and len(idxs) > self.subsample:
            # uniform subsample for speed
            step = len(idxs)/self.subsample
            idxs = [idxs[int(i*step)] for i in range(self.subsample)]
        logps = []
        for i in idxs:
            masked = input_ids.clone()
            masked[i] = self.tok.mask_token_id
            out = self.model(input_ids=masked.unsqueeze(0).to(self.device),
                             attention_mask=attn.unsqueeze(0).to(self.device))
            logits = out.logits[0, i]
            logp = torch.log_softmax(logits, dim=-1)[input_ids[i]].item()
            logps.append(logp)
        if not logps: return 0.0
        return math.exp(-sum(logps)/len(logps))

# ---------- Dataset traversal ----------
rx_file = re.compile(r"^sch_(\d+)_(\d+)(?:_(definite_pins|definite_wires))?\.py$")

def file_type_from_name(name: str) -> str:
    m = rx_file.match(name)
    if not m: return "other"
    tail = m.group(3)
    if tail == "definite_pins": return "pins"
    if tail == "definite_wires": return "wires"
    return "base"

def type_specific_health(ftype: str, canon_text: str) -> Dict[str, float]:
    """Compute simple per-type health metrics from canonical lines."""
    lines = [ln for ln in canon_text.splitlines() if ln.startswith("CALL ")]
    d: Dict[str, float] = {}
    if ftype == "wires":
        # count axis-aligned segments if coordinates look like [x1,y1] and [x2,y2]
        import re as _re, json as _json
        horiz_vert = total = 0
        pat = _re.compile(r"arg0=\[(.+?)\]\s+arg1=\[(.+?)\]")
        for ln in lines:
            if "CALL wire" not in ln: continue
            m = pat.search(ln)
            if not m: continue
            try:
                a = _json.loads("["+m.group(1)+"]"); b = _json.loads("["+m.group(2)+"]")
                if len(a)>=2 and len(b)>=2:
                    total += 1
                    if a[0]==b[0] or a[1]==b[1]: horiz_vert += 1
            except Exception:
                pass
        d["axis_aligned_ratio"] = (horiz_vert/max(1,total))
        d["wire_segments"] = total
    elif ftype == "pins":
        # (ref,pin) 近似统计：从 LIT 或 pinlink 里抓 (ref,pin) 对
        import re as _re
        pair_pat = _re.compile(r'kw:reference="?(?P<ref>[^"\s]+)"?.*?kw:pin(Name|Number)="?(?P<pin>[^"\s]+)"?')
        pairs = []
        for ln in lines:
            m = pair_pat.search(ln)
            if m:
                pairs.append((m.group("ref"), m.group("pin")))
        total = len(pairs)
        uniq = len(set(pairs))
        d["unique_pin_pairs_ratio"] = (uniq/max(1,total))
        d["pin_pairs"] = total
    else:
        # base: ratio of wire calls vs symbol calls
        w = sum(1 for ln in lines if "CALL wire" in ln)
        s = sum(1 for ln in lines if "CALL symbol" in ln)
        d["wire_to_symbol_ratio"] = (w/max(1,s))
        d["wire_calls"] = w
        d["symbol_calls"] = s
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-path", type=str, default=os.environ.get("PROJECT_PATH","."))
    ap.add_argument("--dataset-rel", type=str, default="dataset")
    ap.add_argument("--out", type=str, default="intrinsic_metrics.csv")
    ap.add_argument("--ppl-model", type=str, default="microsoft/codebert-base")
    ap.add_argument("--ppl-maxlen", type=int, default=512)
    ap.add_argument("--ppl-subsample", type=int, default=256)
    args = ap.parse_args()

    root = Path(args.project_path).resolve()/args.dataset_rel
    assert root.exists(), f"Dataset dir not found: {root}"

    ppl = PseudoPPL(model_name=args.ppl_model, max_len=args.ppl_maxlen, subsample=args.ppl_subsample)

    rows: List[Dict[str, Any]] = []
    files = []
    for mod in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for f in mod.iterdir():
            if f.is_file() and f.suffix==".py" and rx_file.match(f.name):
                files.append((mod.name, f))

    for module, path in tqdm(files, desc="Scoring"):
        ftype = file_type_from_name(path.name)
        canon = canonicalize_py(path)
        text = canon.text

        # Compression
        bpb_gzip = gzip_bpb(text)
        bpb_zstd = zstd_bpb(text)
        bits_per_event = (8*len(text.encode("utf-8")))/max(1, canon.stats.get("events",1))
        lz = lz76_norm(text)

        # Pseudo-PPL*
        ppl_star = ppl.ppl(text)

        # Parseability
        parse = dict(
            recognized_call_ratio=canon.stats.get("recognized_call_ratio", 0.0),
            literal_arg_ratio=canon.stats.get("literal_arg_ratio", 0.0),
            nonliteral_arg_rate=canon.stats.get("nonliteral_arg_rate", 0.0),
            events=canon.stats.get("events", 0),
            raw_bytes=canon.stats.get("raw_bytes", 0),
            parse_error=canon.stats.get("parse_error", False),
            total_calls=canon.stats.get("total_calls", 0),
        )

        # Type-specific health
        typem = type_specific_health(ftype, text)

        row = {
            "module": module,
            "file": path.name,
            "type": ftype,
            "ppl_star": ppl_star,
            "gzip_bpb": bpb_gzip,
            "zstd_bpb": (bpb_zstd if bpb_zstd is not None else -1.0),
            "bits_per_event": bits_per_event,
            "lz76_norm": lz,
            **parse,
            **typem,
        }
        rows.append(row)

    # write CSV
    import csv
    out = Path(args.out).resolve()
    with out.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(rows[0].keys()) if rows else []
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows: w.writerow(r)
    print(f"Saved: {out}")

    # quick dataset summaries
    from statistics import mean, median
    by_type: Dict[str, List[Dict[str,Any]]] = {"base":[], "pins":[], "wires":[], "other":[]}
    for r in rows: by_type[r["type"]].append(r)
    def safe_stats(vals): 
        return (median(vals), mean(vals)) if vals else (None, None)
    for t, lst in by_type.items():
        ppls = [r["ppl_star"] for r in lst]
        gz   = [r["gzip_bpb"] for r in lst]
        lz   = [r["lz76_norm"] for r in lst]
        print(f"[{t}] n={len(lst)}  PPL* med/mean={safe_stats(ppls)}  gzip_bpb med/mean={safe_stats(gz)}  lz_norm med/mean={safe_stats(lz)}")

if __name__ == "__main__":
    main()