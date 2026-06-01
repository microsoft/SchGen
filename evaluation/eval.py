#!/usr/bin/env python3

"""Evaluate generated SchGen code stored in a JSONL dataset."""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


PROJECT_PATH = Path(os.environ.get("PROJECT_PATH", Path(__file__).resolve().parents[1]))
os.environ["PROJECT_PATH"] = str(PROJECT_PATH)
sys.path.insert(0, str(PROJECT_PATH))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, 1):
            if line.strip():
                yield line_number, json.loads(line)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate assistant code using SchGen execution, netlist, and ERC metrics."
    )
    parser.add_argument("--input", type=Path, required=True, help="JSONL records with assistant code")
    parser.add_argument("--output", type=Path, required=True, help="JSONL evaluation results")
    parser.add_argument("--limit", type=int, help="Evaluate only the first N records")
    return parser.parse_args()


def mean(values):
    return sum(values) / len(values) if values else None


def main():
    args = parse_args()
    from modules.sch_evaluation import evaluation
    from modules.utils.analyze_json import extract_code, extract_meta_info

    if args.input.resolve() == args.output.resolve():
        raise ValueError("--output must be different from --input")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    code_dir = args.output.parent / f"{args.output.stem}_code"
    code_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    passed = 0
    runtime_errors = []
    netlist_jaccards = []
    netlist_f1_scores = []
    erc_totals = Counter()
    with args.output.open("w", encoding="utf-8") as output_file:
        for index, (line_number, record) in enumerate(iter_jsonl(args.input)):
            if args.limit is not None and index >= args.limit:
                break

            module_name, schematic_name, meta = extract_meta_info(record)
            result = {
                "index": index,
                "input_line": line_number,
                "module": module_name,
                "schematic": schematic_name,
                "style": meta.get("style"),
                "thinking_model": meta.get("thinking_model"),
                "passed": 0,
            }

            try:
                code = extract_code(record)
                code_path = code_dir / f"sample_{index:06d}.py"
                code_path.write_text(code, encoding="utf-8")
                metrics = evaluation(record, str(code_path), code)
                result.update(metrics if isinstance(metrics, dict) else {})
            except Exception as error:
                result["exception"] = f"{type(error).__name__}: {error}"

            total += 1
            passed += int(bool(result.get("passed")))
            if isinstance(result.get("errors"), int):
                runtime_errors.append(result["errors"])
            netlist_metrics = result.get("netlist_evaluation")
            if isinstance(netlist_metrics, dict):
                if isinstance(netlist_metrics.get("jaccard"), (int, float)):
                    netlist_jaccards.append(netlist_metrics["jaccard"])
                if isinstance(netlist_metrics.get("f1_A->B"), (int, float)):
                    netlist_f1_scores.append(netlist_metrics["f1_A->B"])
            erc_errors = result.get("erc_errors")
            if isinstance(erc_errors, dict):
                erc_totals.update({key: value for key, value in erc_errors.items() if isinstance(value, int)})
            output_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            output_file.flush()
            print(f"[{total}] passed={result.get('passed', 0)} {module_name}/{schematic_name}")

    summary = {
        "total": total,
        "execution_passed": passed,
        "execution_pass_rate": passed / total if total else 0.0,
        "mean_runtime_error_lines": mean(runtime_errors),
        "mean_netlist_jaccard": mean(netlist_jaccards),
        "mean_netlist_f1": mean(netlist_f1_scores),
        "mean_erc_errors": {
            key: erc_totals[key] / total for key in sorted(erc_totals)
        },
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"results: {args.output}")
    print(f"summary: {summary_path}")


if __name__ == "__main__":
    main()