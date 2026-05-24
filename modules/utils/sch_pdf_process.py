"""
pdf_axes_cv2.py  –  crop a PDF page and overlay axes (OpenCV-based)
"""

from pathlib import Path
import fitz                              # PyMuPDF
import cv2
import matplotlib.pyplot as plt
import numpy as np


# ---------- rasterise PDF ----------------------------------------------------

def pdf_page_to_cv2(pdf_path: str | Path, page: int = 0, dpi: float = 300) -> np.ndarray:
    """
    Render *page* (0-based) of a PDF to a BGR numpy array (for OpenCV).
    *zoom* controls resolution: 2.0 ≈ 300 dpi for typical A4/letter pages.
    """
    doc = fitz.open(pdf_path)
    pix = doc.load_page(page).get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)  
    return img.copy()                        # detach from buffer



def trim_border(img: np.ndarray, tol: int = 240) -> np.ndarray:
    """
    Remove white-ish border from an image.
    - img: H×W×3 BGR image
    - tol: tolerance [0–255], pixels brighter than tol in all channels count as "background"
    """
    # make a mask of “non-background” pixels
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, tol, 255, cv2.THRESH_BINARY_INV)

    # find all non-zero points, then bounding rect
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return img  # nothing to trim

    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()

    # crop and return
    return img[y0 : y1 + 1, x0 : x1 + 1].copy()

# ---------- basic helpers ----------------------------------------------------

def get_size(img: np.ndarray) -> tuple[int, int]:
    h, w = img.shape[:2]
    return w, h


def center_crop(img: np.ndarray, scale: float = 0.5) -> np.ndarray:
    """Return a centred crop (scale × original size)."""
    h, w = img.shape[:2]
    new_w, new_h = int(w * scale), int(h * scale)
    x0 = (w - new_w) // 2
    y0 = (h - new_h) // 2
    return img[y0 : y0 + new_h, x0 : x0 + new_w].copy()


# ---------- overlay axes with matplotlib -------------------------------------

def overlay_axes(
    img_rgb,                                # H×W×3 array
    x_range=(0,1),                          # (xmin, xmax) in your units
    y_range=(0,1),                          # (ymin, ymax)
    origin="upper-left",                    # "upper-left" or "lower-left"
    xticks=(0,1,0.1),                       # (start, end, step)
    yticks=(0,1,0.1),
    font_size=10,
    show_grid=True,
    grid_kwargs=None,                       # override grid style if you want
    out_path="output.png",
    dpi=300
):
    """
    img_rgb: numpy H×W×3
    x_range, y_range: tuples defining axis span
    origin: where (xmin,ymin) sits on the image
    """
    h, w = img_rgb.shape[:2]

    # build tick arrays
    xt = np.arange(*xticks, dtype=float)
    yt = np.arange(*yticks, dtype=float)

    # decide extent & origin flag
    if origin == "lower-left":
        extent = [*x_range, *y_range]      # [xmin, xmax, ymin, ymax]
        origin_flag = "lower"
        ylim = y_range
    else:
        extent = [*x_range, y_range[1], y_range[0]]  
        origin_flag = "upper"
        ylim = (y_range[1], y_range[0])

    fig, ax = plt.subplots(figsize=(w/dpi, h/dpi), dpi=dpi)
    ax.imshow(img_rgb, extent=extent, origin="upper")
    ax.set_xlim(x_range)
    ax.set_ylim(ylim)

    ax.set_xticks(xt)
    ax.set_yticks(yt)
    ax.set_xlabel("X", fontsize=font_size)
    ax.set_ylabel("Y", fontsize=font_size)
    ax.tick_params(labelsize=font_size)

    if show_grid:
        gk = dict(color="gray", linestyle="--", linewidth=0.5, alpha=0.7)
        gk.update(grid_kwargs or {})
        ax.grid(True, **gk)

    # draw the main axes lines at the data-origin
    ax.axhline(y=y_range[0], color="black", lw=1)
    ax.axvline(x=x_range[0], color="black", lw=1)

    ax.set_aspect("equal")
    ax.set_frame_on(False)
    plt.tight_layout(pad=0)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)



# ---------- quick demo -------------------------------------------------------

if __name__ == "__main__":
    pdf_file = "export/schematic.pdf"      # first page
    img = pdf_page_to_cv2(pdf_file, page=0)
    # img = trim_border(img, tol=240)          # remove white border
    print("Full size:", get_size(img))

    cv2.imwrite("full.png", img)            # save full image
    print("Saved → full.png")

    img_crop = center_crop(img, 0.5)
    print("Crop size:", get_size(img_crop))

    # save the cropped image with adjusted color space
    cv2.imwrite("cropped.png", cv2.cvtColor(img_crop, cv2.COLOR_RGB2BGR))
    print("Saved → cropped.png")

    overlay_axes(
        img_crop,
        x_range=(0,200),
        y_range=(0,150),
        xticks=(0, 200, 10),
        yticks=(0, 150, 10),
        origin="lower-left",
        font_size=8,
        out_path="with_axes.png",
    )
    print("Saved → with_axes.png")
