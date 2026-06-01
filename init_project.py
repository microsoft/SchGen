#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import runpy
from pathlib import Path
import os, sys
import subprocess
import shlex

project_path = os.environ.get("PROJECT_PATH")
if project_path:
    sys.path.append(project_path)
from modules.kicad_sch_interface import set_schematic_filename
from modules.kicad_sch_interface import get_fp
from config import KICAD_SYMBOL_LIB_PATH, KICAD_FOOTPRINT_LIB_PATH, python_path

def run_py(schematic_code: Path):
    env = os.environ.copy()
    env["PROJECT_PATH"] = project_path

    cmd = f'"{sys.executable}" "{schematic_code}"'

    print("Running command:")
    print(cmd)

    res = subprocess.run(
        cmd,
        shell=True,
        cwd=str(project_path),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    print(res.stdout)

    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to run schematic code: {schematic_code}"
        )

def make_kicad_sch() -> str:
    return '''(kicad_sch
    (version 20231120)
    (generator "eeschema")
    (generator_version "8.0")
    (uuid "00000000-0000-0000-0000-000000000000")
    (paper "A4")
    (lib_symbols)
    (sheet_instances
        (path "/"
            (page "1")
        )
    )
    (symbol_instances)
)
'''


def init_kicad_project(project_name: str, overwrite: bool = False) -> tuple[Path, Path, Path]:
    project_dir = Path.cwd() / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    sch_path = project_dir / f"{project_name}.kicad_sch"

    if not overwrite:
        if sch_path.exists():
            raise FileExistsError(f"{p} already exists. Use --overwrite to replace it.")

    sch_path.write_text(make_kicad_sch(), encoding="utf-8")

    return project_dir, sch_path


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a KiCad project and run schematic generation code."
    )
    parser.add_argument("project_name", help="KiCad project name")
    parser.add_argument(
        "schematic_code",
        type=Path,
        help="Python schematic code file to execute",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .kicad_sch file",
    )
    args = parser.parse_args()

    schematic_code = args.schematic_code.resolve()
    if not schematic_code.exists():
        raise FileNotFoundError(f"Schematic code file not found: {schematic_code}")

    project_dir, sch_path = init_kicad_project(
        args.project_name,
        overwrite=args.overwrite,
    )

    # Insert set_schematic_filename(...) into the schematic code before running it.
    code_text = schematic_code.read_text(encoding="utf-8")

    target_import = "from modules.kicad_sch_interface import *"
    insert_line = f'set_schematic_filename(r"{sch_path}")'

    if insert_line not in code_text:
        if target_import not in code_text:
            raise RuntimeError(f"Cannot find import line: {target_import}")

        code_text = code_text.replace(
            target_import,
            f"{target_import}\n{insert_line}",
            1,
        )
        schematic_code.write_text(code_text, encoding="utf-8")

    # Run the schematic code to generate the .kicad_sch file.
    run_py(schematic_code)

    # Search and add footprints for empty symbols
    fps = get_fp(sch_path)
    print(f"{len(fps)} Footprints added")

    print(f"KiCad project initialized at: {project_dir}")
    print(f"Schematic file: {sch_path}")
    print(f"Executed schematic code: {schematic_code}")


if __name__ == "__main__":
    main()