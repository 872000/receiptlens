"""Shared fixtures for the ReceiptLens test suite."""
from pathlib import Path

import pytest

from receiptlens import categorizer

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def rules():
    return categorizer.load_rules(ROOT / "data" / "categories.yaml")


@pytest.fixture()
def receipts_dir():
    return ROOT / "data" / "receipts"


@pytest.fixture()
def demo_texts(receipts_dir):
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(receipts_dir.glob("*.txt"))
    }
