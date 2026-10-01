"""Tests for the pluggable OCR layer."""
import pytest

from receiptlens import ocr


def test_text_file_passthrough(tmp_path):
    target = tmp_path / "receipt.txt"
    target.write_text("HELLO 1.00")
    text, source = ocr.extract_text(target)
    assert text == "HELLO 1.00"
    assert source == "text"


def test_image_falls_back_to_sibling_txt(tmp_path):
    (tmp_path / "scan.txt").write_text("FALLBACK 2.00")
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG fake")
    text, source = ocr.extract_text(image)
    assert text == "FALLBACK 2.00"
    assert source in {"tesseract", "demo-fallback"}


def test_image_without_fallback_raises(tmp_path):
    image = tmp_path / "lonely.png"
    image.write_bytes(b"\x89PNG fake")
    if ocr.tesseract_available():
        pytest.skip("tesseract is installed; fallback path not exercised")
    with pytest.raises(ocr.OCRError):
        ocr.extract_text(image)


def test_unsupported_type_raises(tmp_path):
    target = tmp_path / "doc.pdf"
    target.write_bytes(b"%PDF fake")
    with pytest.raises(ocr.OCRError):
        ocr.extract_text(target)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ocr.OCRError):
        ocr.extract_text(tmp_path / "ghost.txt")
