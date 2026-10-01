"""Pluggable OCR layer.

ReceiptLens prefers the ``tesseract`` binary when it is on ``PATH`` and
OCRs images with it. When tesseract is not available, image inputs fall
back to a same-named ``.txt`` file — which is how the bundled demo
receipts work with zero setup and no network access.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_EXTS = {".txt", ".md", ".text"}


class OCRError(RuntimeError):
    """Raised when text cannot be extracted from an input file."""


def tesseract_available() -> bool:
    """True when the ``tesseract`` binary can be found on ``PATH``."""
    return shutil.which("tesseract") is not None


def supported(path: Path) -> bool:
    """True when *path* is a file type ReceiptLens can ingest."""
    return path.suffix.lower() in IMAGE_EXTS | TEXT_EXTS


def _ocr_with_tesseract(image: Path) -> str:
    proc = subprocess.run(
        ["tesseract", str(image), "stdout", "--psm", "6"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise OCRError(f"tesseract failed on {image.name}: {proc.stderr.strip()}")
    text = proc.stdout.strip()
    if not text:
        raise OCRError(f"tesseract returned no text for {image.name}")
    return text


def extract_text(path: str | Path) -> tuple[str, str]:
    """Extract text from *path*.

    Returns ``(text, source)`` where *source* is one of ``"text"`` (a plain
    text file), ``"tesseract"`` (an OCR'd image) or ``"demo-fallback"`` (an
    image whose paired ``.txt`` file was used because tesseract is not
    installed).
    """
    path = Path(path)
    if not path.is_file():
        raise OCRError(f"file not found: {path}")
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    if ext in IMAGE_EXTS:
        if tesseract_available():
            return _ocr_with_tesseract(path), "tesseract"
        sibling = path.with_suffix(".txt")
        if sibling.is_file():
            return (
                sibling.read_text(encoding="utf-8", errors="replace"),
                "demo-fallback",
            )
        raise OCRError(
            f"tesseract is not installed and no fallback text was found for "
            f"{path.name} (looked for {sibling.name})"
        )
    raise OCRError(f"unsupported file type: {path.suffix or '(none)'}")
