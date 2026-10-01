"""Line-item parser: merchant, date, items, subtotal, tax and total.

The parser is a set of regexes and heuristics tuned for the plain-text
output of receipt OCR — no machine learning, no network, fully
deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_AMOUNT = r"-?[\d,]*\.\d{2}"
_ITEM_RE = re.compile(rf"^(?P<name>.*?)\s+\$?\s*(?P<amount>{_AMOUNT})\s*$")

# Words that mark a line as a receipt summary/footer rather than a
# purchasable line item.
_SUMMARY_WORDS = frozenset(
    {
        "total",
        "subtotal",
        "sub",
        "tax",
        "hst",
        "gst",
        "pst",
        "qst",
        "cash",
        "card",
        "credit",
        "debit",
        "change",
        "balance",
        "tender",
        "tendered",
        "payment",
        "savings",
        "discount",
        "coupon",
        "rounding",
        "items",
    }
)

_TAX_WORDS = re.compile(r"\b(tax|hst|gst|pst|qst)\b", re.IGNORECASE)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class ReceiptItem:
    """A single purchasable line on a receipt."""

    name: str
    price: float


@dataclass
class ParsedReceipt:
    """The structured result of parsing one receipt's text."""

    merchant: str
    date: date | None
    items: list[ReceiptItem] = field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    raw_text: str = ""
    source: str = "text"  # "text" | "tesseract" | "demo-fallback"

    @property
    def balance_ok(self) -> bool:
        """True when subtotal + tax matches the printed total."""
        if self.subtotal is None or self.tax is None or self.total is None:
            return False
        return abs((self.subtotal + self.tax) - self.total) < 0.015


def _parse_amount(text: str) -> float:
    return float(text.replace(",", "").replace("$", ""))


def _is_summary_line(name: str) -> bool:
    tokens = re.findall(r"[a-z]+", name.lower())
    return any(token in _SUMMARY_WORDS for token in tokens)


def _extract_merchant(lines: list[str]) -> str:
    for line in lines:
        cleaned = re.sub(r"^[\*\=\-\~#\s]+|[\*\=\-\~#\s]+$", "", line).strip()
        cleaned = re.sub(r"\s*#\d+\s*$", "", cleaned)  # trailing store numbers
        if not cleaned or re.fullmatch(r"[\W\d_]+", cleaned) or len(cleaned) < 2:
            continue
        if _ITEM_RE.match(line):
            continue  # a line ending in a price is an item, not a header
        return cleaned.title()
    return "Unknown merchant"


def _extract_date(text: str) -> date | None:
    patterns = [
        r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})",  # 2026-09-04
        r"(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4})",  # 09/04/2026
        r"(?P<m>\d{1,2})-(?P<d>\d{1,2})-(?P<y>\d{4})",  # 09-04-2026
        r"(?P<mon>[A-Za-z]{3,9})\s+(?P<d>\d{1,2}),\s*(?P<y>\d{4})",  # Sep 4, 2026
    ]
    for line in text.splitlines():
        for pattern in patterns:
            match = re.search(pattern, line)
            if not match:
                continue
            try:
                parts = match.groupdict()
                if "mon" in parts and parts["mon"]:
                    month = _MONTHS[parts["mon"][:3].lower()]
                else:
                    month = int(parts["m"])
                return date(int(parts["y"]), month, int(parts["d"]))
            except (ValueError, KeyError):
                continue
    return None


def _line_amounts(line: str) -> list[float]:
    return [_parse_amount(m) for m in re.findall(_AMOUNT, line)]


def parse(text: str, source: str = "text") -> ParsedReceipt:
    """Parse receipt *text* into a :class:`ParsedReceipt`."""
    lines = [line for line in (l.strip() for l in text.splitlines()) if line]
    receipt = ParsedReceipt(
        merchant=_extract_merchant(lines),
        date=_extract_date(text),
        raw_text=text,
        source=source,
    )

    for line in lines:
        lowered = line.lower()
        amounts = _line_amounts(line)
        if not amounts:
            continue
        if "subtotal" in lowered or re.search(r"\bsub\s*-?\s*total\b", lowered):
            receipt.subtotal = amounts[-1]
            continue
        if re.search(r"(?<!\bsub)(?<!\bsub\s)\btotal\b", lowered):
            receipt.total = amounts[-1]
            continue
        if _TAX_WORDS.search(line):
            if receipt.tax is None:  # first tax line wins
                receipt.tax = amounts[-1]
            continue
        item_match = _ITEM_RE.match(line)
        if item_match:
            name = item_match.group("name").strip(" -*")
            if name and not _is_summary_line(name):
                receipt.items.append(
                    ReceiptItem(name=name, price=_parse_amount(item_match.group("amount")))
                )
    return receipt
