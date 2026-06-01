import subprocess, platform, shutil
from pathlib import Path


if __name__ == "__main__":
    import sys
    # open config file to get the project path
    with open("./configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        project_path = lines[0].strip()
        sys.path.append(project_path)

# -------- helpers --------
def _find_kicad_cli() -> str:
    """
    Return the full path to kicad-cli, or just 'kicad-cli' if it’s on PATH.
    Adjusts for typical install dirs on macOS and Windows.
    """
    exe = "kicad-cli.exe" if platform.system() == "Windows" else "kicad-cli"
    cli = shutil.which(exe)
    if cli:
        return cli

    if platform.system() == "Darwin":   # macOS default bundle path
        return "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"  # :contentReference[oaicite:0]{index=0}
    else:                               # Windows default
        return r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"

def _run(args):
    """Run kicad‑cli and raise if it fails."""
    subprocess.run([_find_kicad_cli(), *args], check=True)

def convert_sch_to_pcb(sch: str, pcb: str):
    """
    kicad-cli pcb update my_project.kicad_pcb --schematic my_project.kicad_sch
    """
    cmd = ["pcb", "update", str(pcb), "--schematic", str(sch)]  # :contentReference[oaicite:4]{index=4}
    _run(cmd)
    return Path(pcb)