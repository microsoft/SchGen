'''
This module provides utilities to export KiCad schematic and PCB files to various formats (SVG, PDF, netlist, DRC report) using the kicad-cli tool. It includes functions to find the kicad-cli executable, run it with appropriate arguments, and process the exported files (e.g., overlaying axes on the schematic PDF). The module also defines some constants for page size and cropping, and provides example usage of the export functions.
'''
import subprocess, platform, shutil
from pathlib import Path
import os, sys
project_path = os.environ.get("PROJECT_PATH")
sys.path.append(project_path)


from modules.utils.misc import *
from modules.utils.sch_pdf_process import *

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

# -------- public API --------
def export_svg(sch: str | Path, out_dir: str | Path = ".", pages: str | None = None):
    """
    Export a KiCad schematic as SVG files (one per sheet).
    """
    cmd = ["sch", "export", "svg", str(sch), "-o", str(out_dir)]  # :contentReference[oaicite:1]{index=1}
    if pages:
        cmd += ["--pages", pages]
    _run(cmd)
    return Path(out_dir)

def export_pdf(sch: str | Path, out_file: str | Path = "schematic.pdf", pages: str | None = None):
    """
    Export a KiCad schematic as a single multi‑page PDF.
    """
    cmd = ["sch", "export", "pdf", str(sch), "-o", str(out_file)]  # :contentReference[oaicite:2]{index=2}
    if pages:
        cmd += ["--pages", pages]
    _run(cmd)
    return Path(out_file)

def export_pdf_pcb(sch: str | Path, out_file: str | Path = "schematic.pdf", pages: str | None = None):
    """
    Export a KiCad schematic as a single multi‑page PDF.
    """
    cmd = ["pcb", "export", "pdf", str(sch), "-o", str(out_file), "-l", "F.Cu"]  # :contentReference[oaicite:2]{index=2}
    if pages:
        cmd += ["--pages", pages]
    _run(cmd)
    return Path(out_file)


def export_netlist(sch: str | Path, out_file: str | Path = "netlist.net", pages: str | None = None):
    """
    Export a KiCad schematic as a KiCAD netlist file.
    """
    cmd = ["sch", "export", "netlist", str(sch), "-o", str(out_file)]  # :contentReference[oaicite:3]{index=3}
    if pages:
        cmd += ["--pages", pages]
    _run(cmd)
    return Path(out_file)

def export_drc_report(pcb: str | Path, out_file: str | Path = "drc_report.txt"):
    """
    Export a KiCad PCB DRC report file.
    """
    cmd = ["pcb", "drc", "-o", str(out_file), f"{pcb}"]  # :contentReference[oaicite:4]{index=4}
    _run(cmd)
    return Path(out_file)

def export_erc_report(sch: str | Path, out_file: str | Path = "erc_report.txt"):
    """
    Export a KiCad schematic ERC report file.
    """
    cmd = ["sch", "erc", "-o", str(out_file), f"{sch}"]  # :contentReference[oaicite:4]{index=4}
    _run(cmd)
    return Path(out_file)


EXPORT_DIR = Path("export")
EXPORT_DIR.mkdir(exist_ok=True)          # create export dir if it doesn't exist


SCH_X_SIZE = 297 # A4 height in mm
SCH_Y_SIZE = 210 # A4 width in mm

ORIGIN_AXES = False

if ORIGIN_AXES:
    SCH_CROP_SCALE = 1 # crop to 80% of original size

    SCH_AXES_UNITS = 20 # mm
    SCH_AXES_ORIGIN = "upper-left" # origin location of axes
else:
    SCH_CROP_SCALE = 1 # crop to 80% of original size

    SCH_AXES_UNITS = 20 # mm
    SCH_AXES_ORIGIN = "lower-left" # origin location of axes

PCB_AXES_UNITS = 1 

def update_sche_pdf(pdf_filename: str | Path = "schematic.pdf", schematic_path = None):
    """
    Update the schematic PDF file.
    """
    if schematic_path is None:
        sch_file = get_schematic_path()
    else:
        sch_file = schematic_path

    export_pdf(sch_file, out_file=EXPORT_DIR / pdf_filename)
    print(f"Updated {EXPORT_DIR / pdf_filename}")
    return EXPORT_DIR / pdf_filename

def update_pcb_pdf(pdf_filename: str | Path = "pcb.pdf", pcb_path = None):
    """
    Update the PCB PDF file.
    """

    export_pdf_pcb(pcb_path, out_file=EXPORT_DIR / pdf_filename)
    print(f"Updated {EXPORT_DIR / pdf_filename}")
    return EXPORT_DIR / pdf_filename

def rd_by_unit(x, unit):
    """
    Round to the nearest unit.
    """
    return round(x / unit) * unit

def get_sch_with_axes(image_name: str = "sch_with_axes.png", schematic_path: str | Path = None):
    """
    Get a KiCad schematic with axes overlaid.
    """

    pdf_file = update_sche_pdf(schematic_path=schematic_path)

    img = pdf_page_to_cv2(pdf_file, page=0)
    # img = trim_border(img, tol=240)          # remove white border
    print("Full size:", get_size(img))

    img_crop = center_crop(img, SCH_CROP_SCALE)
    print("Crop size:", get_size(img_crop))

    x_range_start = (1-SCH_CROP_SCALE) * SCH_X_SIZE / 2
    y_range_start = (1-SCH_CROP_SCALE) * SCH_Y_SIZE / 2

    x_range_max = x_range_start + SCH_X_SIZE * SCH_CROP_SCALE 
    y_range_max = y_range_start + SCH_Y_SIZE * SCH_CROP_SCALE

    # Round to the nearest unit
    x_range_start = rd_by_unit(x_range_start, SCH_AXES_UNITS)
    y_range_start = rd_by_unit(y_range_start, SCH_AXES_UNITS)
    x_range_max = rd_by_unit(x_range_max, SCH_AXES_UNITS)
    y_range_max = rd_by_unit(y_range_max, SCH_AXES_UNITS)

    out_path = EXPORT_DIR / "sch_images"
    out_path.mkdir(exist_ok=True)

    overlay_axes(
        img_crop,
        x_range=(x_range_start, x_range_max),
        y_range=(y_range_start, y_range_max),
        xticks=(x_range_start, x_range_max +1, SCH_AXES_UNITS),
        yticks=(y_range_start, y_range_max +1, SCH_AXES_UNITS),
        origin=SCH_AXES_ORIGIN,
        font_size=15,
        out_path=out_path / image_name,
    )
    print(f"Saved → {out_path / image_name}")

    return f"{out_path / image_name}"

def get_pcb_with_axes(image_name: str = "pcb_with_axes.png", pcb_path: str | Path = None):
    """
    Get a KiCad schematic with axes overlaid.
    """

    pdf_file = update_pcb_pdf(pdf_filename="pcb.pdf", pcb_path=pcb_path)

    img = pdf_page_to_cv2(pdf_file, page=0)
    # img = trim_border(img, tol=240)          # remove white border
    print("Full size:", get_size(img))

    x_range_start = 12
    y_range_start = 12

    x_range_max = 285
    y_range_max = 198

    out_path = EXPORT_DIR / "pcb_images"
    out_path.mkdir(exist_ok=True)

    overlay_axes(
        img,
        x_range=(x_range_start, x_range_max),
        y_range=(y_range_start, y_range_max),
        origin=SCH_AXES_ORIGIN,
        font_size=15,
        out_path=out_path / image_name,
    )
    print(f"Saved → {out_path / image_name}")

    return f"{out_path / image_name}"


def axes_pos_to_sch_pos(x: float, y: float) -> tuple[float, float]:
    """
    Convert axes position to schematic position.
    """
    if SCH_AXES_ORIGIN == "lower-left":
        x_sch = x * SCH_AXES_UNITS + (1-SCH_CROP_SCALE) * SCH_X_SIZE / 2
        y_sch = -y * SCH_AXES_UNITS + (1-SCH_CROP_SCALE) * SCH_Y_SIZE / 2 + SCH_CROP_SCALE * SCH_Y_SIZE
    elif SCH_AXES_ORIGIN == "upper-left":
        x_sch = x * SCH_AXES_UNITS + (1-SCH_CROP_SCALE) * SCH_X_SIZE / 2
        y_sch = y * SCH_AXES_UNITS + (1-SCH_CROP_SCALE) * SCH_Y_SIZE / 2
    else:
        raise ValueError(f"Unknown axes origin: {SCH_AXES_ORIGIN}")

    return x_sch, y_sch

def get_schematic_netlist(sch_file: str = None, netlist_file: str = "schematic.net") -> str:
    """
    Get the netlist from a KiCad schematic file.
    """
    if sch_file is None:
        sch_file = get_schematic_path()

    export_netlist(sch_file, out_file=netlist_file)
    print(f"Netlist saved to {netlist_file}")

    with open(netlist_file, "r") as f:
        netlist_content = f.read()

    return str(netlist_content)

def get_drc_report(pcb_file: str | Path) -> str:
    """
    Get the DRC report from a KiCad PCB file.
    """
    name = Path(pcb_file).stem
    drc_report_file = Path(pcb_file).parent / f"{name}_drc_report.txt"
    export_drc_report(pcb_file, out_file=drc_report_file)
    print(f"DRC report saved to {drc_report_file}")

    with open(drc_report_file, "r") as f:
        drc_content = f.read()

    return str(drc_content)

def get_erc_report(sch_file: str | Path) -> str:
    """
    Get the ERC report from a KiCad schematic file.
    """
    name = Path(sch_file).stem
    erc_report_file = Path(sch_file).parent / f"{name}_erc_report.txt"
    export_erc_report(sch_file, out_file=erc_report_file)
    print(f"ERC report saved to {erc_report_file}")

    with open(erc_report_file, "r") as f:
        erc_content = f.read()

    return str(erc_content)


# -------- example usage --------
if __name__ == "__main__":
    sch_file = get_schematic_path()
    # 1) vector output you can view anywhere:
    # export_svg(sch_file, out_dir="export")      # → plots/Sheet_1.svg, Sheet_2.svg, …
    # 2) single PDF (nice for email or print):
    export_pdf(sch_file, out_file="export/schematic_test.pdf")

    # 3) netlist file for PCB layout:
    # export_netlist(sch_file, out_file="export/schematic_test.net")

    print("Done.")

    # Test the axes overlay
    # get_sch_with_axes()
