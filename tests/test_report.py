"""Tests for monthly reports and charts."""
import pytest

from receiptlens import parser, report, store


@pytest.fixture()
def sept_db(tmp_path, rules, demo_texts):
    conn = store.connect(tmp_path / "demo.db")
    for text in demo_texts.values():
        store.ingest_receipt(conn, parser.parse(text), rules)
    yield conn, rules
    conn.close()


def test_monthly_totals_add_up(sept_db):
    conn, rules = sept_db
    data = report.monthly_data(conn, 2026, 9, rules)
    assert data["n_receipts"] == 7
    assert data["n_items"] == 25
    assert data["grand_total"] == pytest.approx(250.33)
    # Tax-inclusive category totals must reconcile with receipt totals.
    assert sum(r["total"] for r in data["categories"]) == pytest.approx(250.33, abs=0.05)
    assert data["tax_total"] == pytest.approx(4.75 + 0.95 + 2.72 + 8.81 + 2.96 + 4.87 + 3.74)


def test_monthly_data_august(sept_db):
    conn, rules = sept_db
    data = report.monthly_data(conn, 2026, 8, rules)
    assert data["n_receipts"] == 1
    assert data["grand_total"] == pytest.approx(57.01)
    assert data["merchants"][0]["merchant"] == "Cineplex Odeon"


def test_empty_month(sept_db, capsys):
    conn, rules = sept_db
    data = report.monthly_data(conn, 2021, 1, rules)
    assert data["n_receipts"] == 0
    assert data["categories"] == []
    report.print_report(data)  # must not crash
    assert "No receipts" in capsys.readouterr().out


def test_make_chart_writes_png(sept_db, tmp_path):
    conn, rules = sept_db
    data = report.monthly_data(conn, 2026, 9, rules)
    png = report.make_chart(data, tmp_path / "chart.png")
    assert png.is_file()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.stat().st_size > 10_000


def test_make_chart_empty_month(sept_db, tmp_path):
    conn, rules = sept_db
    data = report.monthly_data(conn, 2021, 1, rules)
    png = report.make_chart(data, tmp_path / "empty.png")
    assert png.is_file()


def test_save_report_writes_md_and_png(sept_db, tmp_path):
    conn, rules = sept_db
    data = report.monthly_data(conn, 2026, 9, rules)
    md_path, png_path = report.save_report(data, tmp_path / "out")
    assert md_path.name == "2026-09-report.md"
    assert png_path.name == "2026-09-spending.png"
    md = md_path.read_text()
    assert "September 2026" in md
    assert "groceries" in md
    assert png_path.is_file()


def test_monthly_data_handles_receipt_without_total(tmp_path, rules):
    """A receipt with items but no printed total must not crash the report;
    category totals gracefully fall back to plain item prices."""
    from datetime import date

    from receiptlens.parser import ParsedReceipt, ReceiptItem

    conn = store.connect(tmp_path / "nototal.db")
    parsed = ParsedReceipt(
        merchant="Corner Deli",
        date=date(2026, 10, 2),
        items=[
            ReceiptItem(name="Turkey sandwich", price=8.50),
            ReceiptItem(name="Coffee", price=2.75),
        ],
        subtotal=11.25,
        tax=None,
        total=None,
        raw_text="corner deli receipt without printed total",
    )
    store.ingest_receipt(conn, parsed, rules)
    data = report.monthly_data(conn, 2026, 10, rules)
    assert data["n_receipts"] == 1
    assert data["grand_total"] == pytest.approx(11.25)
    assert sum(r["total"] for r in data["categories"]) == pytest.approx(11.25)
    conn.close()
