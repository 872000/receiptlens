"""Tests for the rule-based categorizer."""
import pytest

from receiptlens import categorizer


def test_rules_load_in_order(rules):
    names = [r.name for r in rules]
    assert names == [
        "groceries", "dining", "coffee", "transport",
        "shopping", "health", "entertainment",
    ]
    assert all(r.keywords for r in rules)
    assert all(r.color.startswith("#") for r in rules)


@pytest.mark.parametrize(
    "item,expected",
    [
        ("MILK 2% 4L", "groceries"),
        ("BANANAS 1.02KG @ 1.99", "groceries"),  # plural keyword match
        ("EGGS LARGE 12PK", "groceries"),
        ("MED PEPPERONI PIZZA", "dining"),
        ("GARLIC BREAD", "dining"),  # longer keyword beats "bread"
        ("2L PEPSI", "dining"),
        ("2 MED DRINKS", "dining"),
        ("LG COFFEE DARK ROAST", "coffee"),
        ("TRIP FARE", "transport"),
        ("BOOKING FEE", "transport"),
        ("REGULAR GAS 42.310L", "transport"),
        ("CAR WASH BASIC", "transport"),
        ("LED LIGHT BULBS 4PK", "shopping"),
        ("VITAMIN D 1000IU 90CT", "health"),
        ("IBUPROFEN 200MG 100CT", "health"),
        ("BANDAGES ASSORTED", "health"),
        ("ADULT EVENING TICKET", "entertainment"),
        ("LARGE POPCORN", "entertainment"),  # beats dining's "pop"
        ("WORK GLOVES", "uncategorized"),
        ("AA BATTERIES 24PK", "uncategorized"),
        ("SOME RANDOM THING", "uncategorized"),
    ],
)
def test_categorize(rules, item, expected):
    assert categorizer.categorize(item, rules) == expected


def test_keyword_boundaries(rules):
    # "tea" must not match inside "steak"; "egg" must not match "eggplant"... it
    # does match by design (\w* suffix) — the boundary that matters is the left one.
    assert categorizer.categorize("STEAK DINNER", rules) != "coffee"
    assert categorizer.categorize("CABANA TOWEL", rules) == "uncategorized"


def test_load_rules_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: [valid\n  oops: 1\n")
    with pytest.raises(ValueError):
        categorizer.load_rules(bad)
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        categorizer.load_rules(missing)
    empty = tmp_path / "empty.yaml"
    empty.write_text("# nothing here\n")
    with pytest.raises(ValueError):
        categorizer.load_rules(empty)
