"""SQLite store for receipts, line items and their categories."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from . import categorizer, parser

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant     TEXT NOT NULL,
    date         TEXT,                       -- ISO YYYY-MM-DD, may be NULL
    subtotal     REAL,
    tax          REAL,
    total        REAL,
    source       TEXT NOT NULL DEFAULT 'text',
    content_hash TEXT NOT NULL UNIQUE,       -- de-duplicates re-ingests
    raw_text     TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    price      REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'uncategorized'
);
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date);
CREATE INDEX IF NOT EXISTS idx_items_receipt ON items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite database at *db_path*."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def ingest_receipt(
    conn: sqlite3.Connection,
    parsed: parser.ParsedReceipt,
    rules: list[categorizer.CategoryRule],
) -> int | None:
    """Store a parsed receipt and its auto-categorized items.

    Returns the new receipt id, or ``None`` when an identical receipt was
    already ingested (matched by content hash).
    """
    digest = content_hash(parsed.raw_text)
    row = conn.execute(
        "SELECT id FROM receipts WHERE content_hash = ?", (digest,)
    ).fetchone()
    if row:
        return None

    cursor = conn.execute(
        """INSERT INTO receipts
           (merchant, date, subtotal, tax, total, source, content_hash, raw_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            parsed.merchant,
            parsed.date.isoformat() if parsed.date else None,
            parsed.subtotal,
            parsed.tax,
            parsed.total,
            parsed.source,
            digest,
            parsed.raw_text,
        ),
    )
    receipt_id = cursor.lastrowid
    conn.executemany(
        "INSERT INTO items (receipt_id, name, price, category) VALUES (?, ?, ?, ?)",
        [
            (
                receipt_id,
                item.name,
                item.price,
                categorizer.categorize(item.name, rules),
            )
            for item in parsed.items
        ],
    )
    conn.commit()
    return receipt_id


def get_receipts(
    conn: sqlite3.Connection, year: int | None = None, month: int | None = None
) -> list[sqlite3.Row]:
    """Receipts, optionally filtered to a calendar month, newest first."""
    if year is not None and month is not None:
        prefix = f"{year:04d}-{month:02d}"
        return conn.execute(
            "SELECT * FROM receipts WHERE date LIKE ? || '-%' ORDER BY date DESC, id DESC",
            (prefix,),
        ).fetchall()
    return conn.execute("SELECT * FROM receipts ORDER BY date DESC, id DESC").fetchall()


def get_items(conn: sqlite3.Connection, receipt_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE receipt_id = ? ORDER BY id", (receipt_id,)
    ).fetchall()


def review_queue(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Items the categorizer could not place, with their receipt context."""
    return conn.execute(
        """SELECT items.id, items.name, items.price,
                  receipts.merchant, receipts.date, receipts.id AS receipt_id
           FROM items JOIN receipts ON receipts.id = items.receipt_id
           WHERE items.category = ?
           ORDER BY receipts.date DESC, items.id""",
        (categorizer.UNCATEGORIZED,),
    ).fetchall()


def recategorize(conn: sqlite3.Connection, item_id: int, category: str) -> bool:
    """Move one item to *category*. Returns True when the item existed."""
    cursor = conn.execute(
        "UPDATE items SET category = ? WHERE id = ?", (category, item_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def category_overview(
    conn: sqlite3.Connection, year: int | None = None, month: int | None = None
) -> list[sqlite3.Row]:
    """Per-category item counts and pre-tax totals, optionally for one month."""
    if year is not None and month is not None:
        prefix = f"{year:04d}-{month:02d}"
        return conn.execute(
            """SELECT items.category AS category,
                      COUNT(*) AS n_items,
                      ROUND(SUM(items.price), 2) AS total
               FROM items JOIN receipts ON receipts.id = items.receipt_id
               WHERE receipts.date LIKE ? || '-%'
               GROUP BY items.category
               ORDER BY total DESC""",
            (prefix,),
        ).fetchall()
    return conn.execute(
        """SELECT category, COUNT(*) AS n_items, ROUND(SUM(price), 2) AS total
           FROM items GROUP BY category ORDER BY total DESC"""
    ).fetchall()


def stats(conn: sqlite3.Connection) -> dict:
    """Small database summary used by the CLI."""
    row = conn.execute(
        "SELECT COUNT(*) AS n_receipts, COUNT(DISTINCT merchant) AS n_merchants,"
        " MIN(date) AS first_date, MAX(date) AS last_date FROM receipts"
    ).fetchone()
    n_items = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
    return {
        "receipts": row["n_receipts"],
        "items": n_items,
        "merchants": row["n_merchants"],
        "first_date": row["first_date"],
        "last_date": row["last_date"],
    }
