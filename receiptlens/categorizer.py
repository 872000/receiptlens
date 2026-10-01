"""Rule-based categorizer with a human-editable keyword rules file.

Rules live in ``data/categories.yaml`` (see that file for the format).
Each category lists keywords; an item scores the sum of the lengths of the
keywords it matches (longer, more specific keywords win ties), and the
highest-scoring category wins. Items that match nothing land in the
``"uncategorized"`` review queue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

UNCATEGORIZED = "uncategorized"
DEFAULT_COLOR = "#90a4ae"


@dataclass
class CategoryRule:
    """One category and the keywords that trigger it."""

    name: str
    keywords: tuple[str, ...] = ()
    color: str = DEFAULT_COLOR
    _patterns: list[re.Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        # `\bkw\w*` so "banana" also matches "bananas", without matching
        # "cabana" or "plantainbanana".
        self._patterns = [
            re.compile(r"\b" + re.escape(kw.lower()) + r"\w*")
            for kw in self.keywords
        ]

    def score(self, item_name: str) -> int:
        text = item_name.lower()
        return sum(
            len(kw) for kw, pat in zip(self.keywords, self._patterns) if pat.search(text)
        )


def load_rules(path: str | Path) -> list[CategoryRule]:
    """Load category rules from a small YAML-subset file.

    Format::

        groceries:
          keywords: [milk, bread, eggs]
          color: "#43a047"

    Full-line comments (``# ...``) and blank lines are ignored. Inline
    comments are not supported.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"category rules not found: {path}")

    rules: list[CategoryRule] = []
    name: str | None = None
    keywords: list[str] = []
    color = DEFAULT_COLOR

    def flush() -> None:
        if name is not None:
            rules.append(CategoryRule(name=name, keywords=tuple(keywords), color=color))

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw[0].isspace():
            flush()
            match = re.match(r"^([A-Za-z0-9 _-]+):\s*$", stripped)
            if not match:
                raise ValueError(f"{path}:{lineno}: expected 'name:' got {stripped!r}")
            name, keywords, color = match.group(1).strip(), [], DEFAULT_COLOR
        else:
            if name is None:
                raise ValueError(f"{path}:{lineno}: indented line before any category")
            if stripped.startswith("keywords:"):
                value = stripped[len("keywords:"):].strip()
                match = re.match(r"^\[(.*)\]$", value)
                if not match:
                    raise ValueError(
                        f"{path}:{lineno}: keywords must be an inline list: [a, b]"
                    )
                keywords = [
                    item.strip().strip("'\"")
                    for item in match.group(1).split(",")
                    if item.strip()
                ]
            elif stripped.startswith("color:"):
                color = stripped[len("color:"):].strip().strip("'\"")
            else:
                raise ValueError(f"{path}:{lineno}: unknown key {stripped!r}")
    flush()

    if not rules:
        raise ValueError(f"{path}: no categories defined")
    return rules


def categorize(item_name: str, rules: list[CategoryRule]) -> str:
    """Return the best-matching category name for *item_name*."""
    best_name = UNCATEGORIZED
    best_score = 0
    for rule in rules:
        score = rule.score(item_name)
        if score > best_score:
            best_name, best_score = rule.name, score
    return best_name
