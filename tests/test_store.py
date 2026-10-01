"""Tests for the SQLite store."""
import pytest

from receiptlens import categorizer, parser, store


@pytest.fixture()
def db(tmp_path, rules):
    conn = store.connect(tmp_path / "test.db")
    yield conn, rules
    conn.close()


def _ingest_all(conn, rules, demo_texts):
    ids = []
    for text in demo_texts.values():
        rid = store.ingest_receipt(conn, parser.parse(text), rules)
        ids.append(rid)
    return ids


def test_ingest_and_dedupe(db, demo_texts):
    conn, rules = db
    ids = _ingest_all(conn, rules, demo_texts)
    assert all(isinstance(i, int) for i in ids)
    # Ingesting everything again must be a no-op (content-hash dedupe).
    again = _ingest_all(conn, rules, demo_texts)
    assert again == [None] * len(ids)
    assert store.stats(conn)["receipts"] == len(ids)


def test_items_are_categorized(db, demo_texts):
    conn, rules = db
    _ingest_all(conn, rules, demo_texts)
    cats = {row["category"] for row in conn.execute("SELECT DISTINCT category FROM items")}
    assert {"groceries", "dining", "coffee", "transport", "shopping", "health",
            "entertainment", "uncategorized"} <= cats


def test_month_filter(db, demo_texts):
    conn, rules = db
    _ingest_all(conn, rules, demo_texts)
    sept = store.get_receipts(conn, 2026, 9)
    assert len(sept) == 7
    assert {r["merchant"] for r in sept} == {
        "Fortinos", "Tim Hortons", "Uber", "Shell",
        "Pizza Pizza", "Canadian Tire", "Shoppers Drug Mart",
    }
    assert len(store.get_receipts(conn, 2026, 8)) == 1
    assert store.get_receipts(conn, 2020, 1) == []


def test_review_queue_and_recategorize(db, demo_texts):
    conn, rules = db
    _ingest_all(conn, rules, demo_texts)
    queue = store.review_queue(conn)
    assert {row["name"] for row in queue} == {"WORK GLOVES", "AA BATTERIES 24PK"}

    item_id = queue[0]["id"]
    assert store.recategorize(conn, item_id, "shopping") is True
    assert store.recategorize(conn, 999999, "shopping") is False
    remaining = {row["name"] for row in store.review_queue(conn)}
    assert queue[0]["name"] not in remaining


def test_category_overview(db, demo_texts):
    conn, rules = db
    _ingest_all(conn, rules, demo_texts)
    overview = {r["category"]: r for r in store.category_overview(conn, 2026, 9)}
    assert overview["groceries"]["n_items"] == 7
    assert overview["groceries"]["total"] == pytest.approx(36.53)
    assert overview["uncategorized"]["n_items"] == 2


def test_stats(db, demo_texts):
    conn, rules = db
    _ingest_all(conn, rules, demo_texts)
    stats = store.stats(conn)
    assert stats["receipts"] == 8
    assert stats["items"] == 29
    assert stats["first_date"] == "2026-08-29"
    assert stats["last_date"] == "2026-09-23"


def test_receipt_without_date_still_ingests(db, rules):
    conn, _ = db
    rid = store.ingest_receipt(conn, parser.parse("SHOP\nWIDGET 3.50"), rules)
    assert isinstance(rid, int)
    row = conn.execute("SELECT date FROM receipts WHERE id = ?", (rid,)).fetchone()
    assert row["date"] is None
