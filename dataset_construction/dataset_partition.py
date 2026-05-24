import os
import sys
import json
import argparse
import hashlib
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_PATH = Path(os.environ["PROJECT_PATH"])
sys.path.append(str(PROJECT_PATH))
from modules.kicad_sch_interface import * 
import my_skip_lib
import random


def extract_symbol_name(component):
    lib_id = component.lib_id.value
    if ":" in lib_id:
        _, symbol_name = lib_id.split(":", 1)
    else:
        symbol_name = ""
    return symbol_name


def extract_label_text(label):
    return label.value if hasattr(label, "value") else label.value


def schematic_type_signature_from_path(sch_path: str):
    """
    Return a signature that represents the "type" of a schematic, based on its components and labels.
    - For components, we use the symbol name (extracted from lib_id).
    - For labels, we use the label text.
    """
    sch = my_skip_lib.Schematic(str(sch_path))

    sym_counter = Counter()
    for comp in getattr(sch, "symbol", []):
        sym_name = extract_symbol_name(comp)
        sym_counter[sym_name] += 1

    lbl_counter = Counter()
    for glb in getattr(sch, "global_label", []):
        lbl_counter[extract_label_text(glb)] += 1


    sym_sig = tuple(sorted(sym_counter.items()))
    lbl_sig = tuple(sorted(lbl_counter.items()))
    return (("SYM", sym_sig), ("LBL", lbl_sig))


def signature_to_type_id(signature) -> str:
    """
    Compress the signature into a short string ID using hashing. This allows us to group schematics by type without storing the full signature.
    """
    raw = json.dumps(signature, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def iter_jsonl_records(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield ln, json.loads(line)
            except Exception as e:
                raise RuntimeError(f"JSON parse failed at {path}:{ln}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="input jsonl path")
    ap.add_argument("--threshold", type=int, default=30)
    ap.add_argument("--cache", default="")
    args = ap.parse_args()

    in_path = Path(args.input)
    threshold = args.threshold

    # Auto output paths
    train_path = in_path.with_name(in_path.stem + ".train.jsonl")
    test_path = in_path.with_name(in_path.stem + ".test.jsonl")
    summary_path = in_path.with_name(in_path.stem + ".summary.json")

    # Cache
    cache_path = Path(args.cache) if args.cache else None
    type_cache = {}
    if cache_path and cache_path.exists():
        type_cache = json.loads(cache_path.read_text(encoding="utf-8"))

    bucket_count = defaultdict(int)
    type_to_records = defaultdict(list)

    kept, dropped, failed = 0, 0, 0
    all_records = []

    # ONLY read input (no writing here!)
    for ln, rec in iter_jsonl_records(in_path):
        try:
            meta = rec.get("meta", {})
            sch_path = meta.get("schematic_path") or meta.get("schematic")
            if not sch_path:
                failed += 1
                continue

            style = meta.get("style", "unknown_style")
            model = meta.get("thinking_model", "unknown_model")

            if sch_path in type_cache:
                type_id = type_cache[sch_path]
            else:
                sig = schematic_type_signature_from_path(sch_path)
                type_id = signature_to_type_id(sig)
                type_cache[sch_path] = type_id

            key = (style, model, type_id)
            if bucket_count[key] < threshold:
                bucket_count[key] += 1
                all_records.append(rec)
                kept += 1

                type_to_records[key].append({
                    "input_line": ln,
                    "module": meta.get("module"),
                    "schematic": meta.get("schematic"),
                    "schematic_path": sch_path,
                    "code_path": meta.get("code_path"),
                })
            else:
                dropped += 1

        except Exception:
            failed += 1

    # Split
    random.shuffle(all_records)
    test_count = min(500, len(all_records))
    test_records = all_records[:test_count]
    train_records = all_records[test_count:]

    # Write outputs
    with train_path.open("w", encoding="utf-8") as f:
        for rec in train_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with test_path.open("w", encoding="utf-8") as f:
        for rec in test_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Cache save
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(type_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # Summary
    summary = []
    for (style, model, type_id), cnt in sorted(bucket_count.items(), key=lambda x: (-x[1], x[0])):
        items = type_to_records[(style, model, type_id)]
        summary.append({
            "style": style,
            "thinking_model": model,
            "type_id": type_id,
            "kept_count": cnt,
            "examples": items[:5],
        })

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("==== Done ====")
    print(f"input:   {in_path}")
    print(f"train:   {train_path} ({len(train_records)} records)")
    print(f"test:    {test_path} ({len(test_records)} records)")
    print(f"summary: {summary_path}")
    print(f"threshold per (style,model,type): {threshold}")
    print(f"kept={kept}, dropped={dropped}, failed={failed}")
    print(f"unique buckets kept: {len(bucket_count)}")


if __name__ == "__main__":
    main()