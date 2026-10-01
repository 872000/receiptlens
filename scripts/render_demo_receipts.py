"""Render mock "scanned" receipt images from the bundled demo receipt texts.

The PNGs are stand-ins for real phone photos: ReceiptLens ingests them
through the same image path as any photo, falling back to the paired
``.txt`` when tesseract is not installed.

Usage:  python scripts/render_demo_receipts.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS = ROOT / "data" / "receipts"

# (source text, output image) — image falls back to the same-named .txt
PAIRS = [
    ("2026-09-04-fortinos.txt", "2026-09-04-fortinos.png"),
    ("2026-09-14-pizza-pizza.txt", "2026-09-14-pizza-pizza.png"),
]


def render(text_path: Path, image_path: Path) -> None:
    import matplotlib.pyplot as plt

    lines = text_path.read_text(encoding="utf-8").splitlines()
    # Slightly uneven line spacing + rotation sells the "photo of paper" look.
    fig, ax = plt.subplots(figsize=(4.2, 6.2), dpi=150)
    fig.patch.set_facecolor("#3a3f4a")  # table surface
    ax.set_facecolor("#fdfdf8")  # receipt paper
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Paper rectangle with a soft edge.
    ax.add_patch(
        plt.Rectangle((0.06, 0.03), 0.88, 0.94, facecolor="#fdfdf8",
                      edgecolor="#d8d8d0", linewidth=1.5, zorder=1)
    )
    body = "\n".join(lines)
    ax.text(
        0.5, 0.97, body, transform=ax.transAxes, fontsize=7.2,
        fontfamily="monospace", va="top", ha="center", color="#1c1c1c",
        linespacing=1.55, zorder=2,
    )
    # Zig-zag "torn" bottom edge.
    import numpy as np

    xs = np.linspace(0.06, 0.94, 40)
    ys = 0.03 + 0.012 * (np.arange(40) % 2)
    ax.fill_between(xs, 0.015, ys, color="#3a3f4a", zorder=3, linewidth=0)

    for text_obj in ax.texts:
        text_obj.set_rotation(0.6)  # barely-there camera tilt
    fig.savefig(image_path, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"wrote {image_path.relative_to(ROOT)}")


def main() -> int:
    missing = [src for src, _ in PAIRS if not (RECEIPTS / src).is_file()]
    if missing:
        print(f"missing source texts: {missing}", file=sys.stderr)
        return 1
    for src, dest in PAIRS:
        render(RECEIPTS / src, RECEIPTS / dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
