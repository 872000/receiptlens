"""Tests for the line-item parser."""
from datetime import date

import pytest

from receiptlens import parser


EXPECTED = {
    # filename: (merchant, date, n_items, subtotal, tax, total)
    "2026-08-29-cineplex.txt": ("Cineplex Odeon", date(2026, 8, 29), 4, 50.45, 6.56, 57.01),
    "2026-09-04-fortinos.txt": ("Fortinos", date(2026, 9, 4), 7, 36.53, 4.75, 41.28),
    "2026-09-06-tim-hortons.txt": ("Tim Hortons", date(2026, 9, 6), 4, 7.27, 0.95, 8.22),
    "2026-09-08-uber.txt": ("Uber", date(2026, 9, 8), 2, 20.95, 2.72, 23.67),
    "2026-09-11-shell.txt": ("Shell", date(2026, 9, 11), 2, 67.78, 8.81, 76.59),
    "2026-09-14-pizza-pizza.txt": ("Pizza Pizza", date(2026, 9, 14), 3, 22.77, 2.96, 25.73),
    "2026-09-19-canadian-tire.txt": ("Canadian Tire", date(2026, 9, 19), 3, 37.47, 4.87, 42.34),
    "2026-09-23-shoppers.txt": ("Shoppers Drug Mart", date(2026, 9, 23), 4, 28.76, 3.74, 32.50),
}


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_demo_receipts_parse(demo_texts, filename):
    merchant, day, n_items, subtotal, tax, total = EXPECTED[filename]
    parsed = parser.parse(demo_texts[filename])
    assert parsed.merchant == merchant
    assert parsed.date == day
    assert len(parsed.items) == n_items
    assert parsed.subtotal == pytest.approx(subtotal)
    assert parsed.tax == pytest.approx(tax)
    assert parsed.total == pytest.approx(total)
    assert parsed.balance_ok


def test_items_have_names_and_positive_prices(demo_texts):
    for text in demo_texts.values():
        for item in parser.parse(text).items:
            assert item.name.strip()
            assert item.price > 0


def test_summary_lines_are_not_items():
    parsed = parser.parse(
        "STORE\n2026-09-01\n\nWIDGET 1.00\nSUBTOTAL 1.00\nTAX 0.13\n"
        "TOTAL 1.13\nCASH 2.00\nCHANGE 0.87\n"
    )
    assert [i.name for i in parsed.items] == ["WIDGET"]


def test_date_formats():
    assert parser.parse("SHOP\n09/04/2026\nA 1.00").date == date(2026, 9, 4)
    assert parser.parse("SHOP\n2026-09-04\nA 1.00").date == date(2026, 9, 4)
    assert parser.parse("SHOP\n09-04-2026\nA 1.00").date == date(2026, 9, 4)
    assert parser.parse("SHOP\nSep 4, 2026\nA 1.00").date == date(2026, 9, 4)
    assert parser.parse("SHOP\nno date here\nA 1.00").date is None


def test_merchant_cleanup():
    assert parser.parse("*** FORTINOS ***\nA 1.00").merchant == "Fortinos"
    assert parser.parse("TIM HORTONS #4521\nA 1.00").merchant == "Tim Hortons"
    assert parser.parse("\n\n   \nA 1.00").merchant == "Unknown merchant"


def test_empty_text():
    parsed = parser.parse("")
    assert parsed.merchant == "Unknown merchant"
    assert parsed.items == []
    assert not parsed.balance_ok
