#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_PATH = Path(os.environ.get("PROJECT_PATH", Path(__file__).resolve().parents[1]))
os.environ.setdefault("PROJECT_PATH", str(PROJECT_PATH))
sys.path.insert(0, str(PROJECT_PATH))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, 1):
            if line.strip():
                yield line_number, json.loads(line)


def schematic_signature(schematic_path: Path):
    """Return a conservative structural fingerprint for a source design."""
    import my_skip_lib

    schematic = my_skip_lib.Schematic(str(schematic_path))

    symbols = Counter()
    for symbol in getattr(schematic, "symbol", []):
        lib_id = symbol.lib_id.value
        symbols[lib_id.split(":", 1)[-1]] += 1

    global_labels = Counter()
    for label in getattr(schematic, "global_label", []):
        global_labels[label.value] += 1

    return {
        "symbols": sorted(symbols.items()),
        "global_labels": sorted(global_labels.items()),
    }


def design_id(record, input_path: Path, cache):
    meta = record.get("meta", {})
    if meta.get("design_id"):
        return str(meta["design_id"])
    if meta.get("type_id"):
        return str(meta["type_id"])

    raw_path = meta.get("schematic_path") or meta.get("schematic")
    if not raw_path:
        raise ValueError("record has no meta.schematic_path or meta.schematic")

    schematic_path = Path(raw_path).expanduser()
    if not schematic_path.is_absolute():
        candidates = [input_path.parent / schematic_path, PROJECT_PATH / schematic_path]
        schematic_path = next((path for path in candidates if path.exists()), candidates[0])
    schematic_path = schematic_path.resolve()

    cache_key = str(schematic_path)
    if cache_key not in cache:
        signature = schematic_signature(schematic_path)
        encoded = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
        cache[cache_key] = hashlib.sha256(encoded).hexdigest()
    return cache[cache_key]


def choose_test_designs(group_sizes, target_samples, seed):
    """Choose complete design groups whose total is close to target_samples."""
    rng = random.Random(seed)
    groups = list(group_sizes.items())
    rng.shuffle(groups)
    if not groups or target_samples == 0:
        return set(), 0

    max_group_size = max(len(records) for _, records in groups)
    max_total = target_samples + max_group_size
    reachable = {0: ()}

    for group_id, records in groups:
        group_size = len(records)
        additions = {}
        for sample_count, selected in reachable.items():
            candidate_count = sample_count + group_size
            if candidate_count <= max_total and candidate_count not in reachable:
                additions.setdefault(candidate_count, selected + (group_id,))
        reachable.update(additions)

    sample_count, selected = min(
        ((count, selected) for count, selected in reachable.items() if selected),
        key=lambda item: (abs(item[0] - target_samples), item[0] > target_samples, item[0]),
    )
    return set(selected), sample_count


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split a SchGen JSONL dataset while keeping each design entirely in train or test."
    )
    parser.add_argument("--input", type=Path, required=True, help="Input JSONL dataset")
    parser.add_argument("--output-prefix", type=Path, required=True, help="Output path prefix")
    parser.add_argument("--target-test-samples", type=int, default=500)
    parser.add_argument("--max-per-variant", type=int, default=30,
                        help="Maximum records per (style, thinking model, design)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache", type=Path, help="Optional schematic-path to design-id cache")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.target_test_samples < 0 or args.max_per_variant < 1:
        raise ValueError("target-test-samples must be nonnegative and max-per-variant must be positive")

    cache = {}
    if args.cache and args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))

    groups = defaultdict(list)
    variant_counts = defaultdict(int)
    dropped = 0

    for line_number, record in iter_jsonl(args.input):
        try:
            group_id = design_id(record, args.input, cache)
        except Exception as error:
            raise RuntimeError(f"failed to identify design at {args.input}:{line_number}: {error}") from error

        meta = record.setdefault("meta", {})
        meta["design_id"] = group_id
        variant = (meta.get("style"), meta.get("thinking_model"), group_id)
        if variant_counts[variant] >= args.max_per_variant:
            dropped += 1
            continue
        variant_counts[variant] += 1
        groups[group_id].append(record)

    test_designs, _ = choose_test_designs(groups, args.target_test_samples, args.seed)
    train_records = []
    test_records = []
    train_designs = set(groups) - test_designs

    for group_id, records in groups.items():
        (test_records if group_id in test_designs else train_records).extend(records)

    assert train_designs.isdisjoint(test_designs)
    assert {record["meta"]["design_id"] for record in train_records}.isdisjoint(
        {record["meta"]["design_id"] for record in test_records}
    )

    rng = random.Random(args.seed)
    rng.shuffle(train_records)
    rng.shuffle(test_records)

    train_path = Path(f"{args.output_prefix}.train.jsonl")
    test_path = Path(f"{args.output_prefix}.test.jsonl")
    summary_path = Path(f"{args.output_prefix}.split_summary.json")
    write_jsonl(train_path, train_records)
    write_jsonl(test_path, test_records)

    summary = {
        "seed": args.seed,
        "target_test_samples": args.target_test_samples,
        "train_samples": len(train_records),
        "test_samples": len(test_records),
        "train_designs": len(train_designs),
        "test_designs": len(test_designs),
        "dropped_by_variant_cap": dropped,
        "test_design_ids": sorted(test_designs),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.cache:
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"train: {train_path}")
    print(f"test: {test_path}")


if __name__ == "__main__":
    main()