"""Command-line interface: ingest, report, categories, recategorize."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, categorizer, ocr, parser, report, store

PACKAGE_DIR = Path(__file__).resolve().parent


def resolve_rules(explicit: str | None) -> Path:
    """Find the category rules file: --rules flag, ./data, repo data/, package."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates += [
        Path("data/categories.yaml"),
        PACKAGE_DIR.parent / "data" / "categories.yaml",
        PACKAGE_DIR / "categories.yaml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "category rules not found; pass --rules PATH or keep data/categories.yaml "
        "next to the project"
    )


def collect_inputs(paths: list[str]) -> list[Path]:
    """Expand CLI paths (files or directories) into a sorted file list."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(p for p in sorted(path.rglob("*")) if p.is_file() and ocr.supported(p))
        elif path.is_file():
            if ocr.supported(path):
                found.append(path)
            else:
                print(f"  !! {path}: unsupported file type, skipped")
        else:
            print(f"  !! {raw}: no such file or directory, skipped")
    # De-duplicate while keeping order (e.g. overlapping dir + file args).
    return list(dict.fromkeys(found))


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_s, month_s = value.split("-")
        year, month = int(year_s), int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"month must look like YYYY-MM, got {value!r}"
        ) from None


def cmd_ingest(args: argparse.Namespace) -> int:
    rules = categorizer.load_rules(resolve_rules(args.rules))
    conn = store.connect(args.db)
    inputs = collect_inputs(args.paths)
    if not inputs:
        print("Nothing to ingest.")
        return 1

    engine = "tesseract" if ocr.tesseract_available() else (
        "not found — images will use their bundled demo text"
    )
    print(f"OCR engine: {engine}")

    ingested = skipped = failed = 0
    for path in inputs:
        try:
            text, source = ocr.extract_text(path)
        except ocr.OCRError as exc:
            print(f"  !! {path.name}: {exc}")
            failed += 1
            continue
        parsed = parser.parse(text, source=source)
        receipt_id = store.ingest_receipt(conn, parsed, rules)
        if receipt_id is None:
            print(f"  -- {path.name}: duplicate of an ingested receipt, skipped")
            skipped += 1
            continue
        date_s = parsed.date.isoformat() if parsed.date else "no date"
        total_s = f"${parsed.total:.2f}" if parsed.total is not None else "no total"
        flag = "" if parsed.balance_ok else "  [totals don't balance]"
        print(f"  ++ {path.name}: {parsed.merchant} · {date_s} · "
              f"{len(parsed.items)} items · {total_s} [{source}]{flag}")
        ingested += 1

    print(f"\nIngested {ingested} receipt(s), skipped {skipped} duplicate(s), "
          f"failed {failed} -> {args.db}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    year, month = args.month
    rules = categorizer.load_rules(resolve_rules(args.rules))
    conn = store.connect(args.db)
    data = report.monthly_data(conn, year, month, rules)
    report.print_report(data)
    if data["n_receipts"]:
        md_path, png_path = report.save_report(data, args.out)
        print(f"\nSaved report: {md_path}\nSaved chart:  {png_path}")
    return 0


def cmd_categories(args: argparse.Namespace) -> int:
    rules = categorizer.load_rules(resolve_rules(args.rules))
    conn = store.connect(args.db)

    if args.review:
        queue = store.review_queue(conn)
        if not queue:
            print("Review queue is empty — everything is categorized. Nice.")
            return 0
        print(f"Uncategorized items ({len(queue)}): fix with "
              "`receiptlens recategorize ITEM_ID CATEGORY`\n")
        print(f"  {'ID':>4}  {'Price':>7}  Item / receipt")
        for row in queue:
            date_s = row["date"] or "no date"
            print(f"  {row['id']:>4}  ${row['price']:>6.2f}  {row['name']}")
            print(f"         from {row['merchant']} on {date_s}")
        return 0

    month_filter = args.month if args.month else (None, None)
    overview = store.category_overview(conn, *month_filter)
    label = f" for {args.month[0]:04d}-{args.month[1]:02d}" if args.month else " (all time)"
    print(f"Categories{label}:\n")
    print(f"  {'Category':<16}{'Items':>7}{'Total':>12}  Keywords")
    print("  " + "-" * 60)
    by_name = {r.name: r for r in rules}
    for row in overview:
        rule = by_name.get(row["category"])
        keywords = ", ".join(rule.keywords[:6]) + ("…" if rule and len(rule.keywords) > 6 else "") if rule else "—"
        print(f"  {row['category']:<16}{row['n_items']:>7}${row['total']:>11.2f}  {keywords}")
    known = {r.name for r in rules}
    missing = known - {row["category"] for row in overview}
    for name in sorted(missing):
        rule = by_name[name]
        keywords = ", ".join(rule.keywords[:6]) + ("…" if len(rule.keywords) > 6 else "")
        print(f"  {name:<16}{0:>7}${0:>11.2f}  {keywords}")
    return 0


def cmd_recategorize(args: argparse.Namespace) -> int:
    conn = store.connect(args.db)
    if store.recategorize(conn, args.item_id, args.category):
        print(f"Item {args.item_id} -> {args.category}")
        return 0
    print(f"No item with id {args.item_id}.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="receiptlens",
        description="Receipt OCR to auto-categorized spending dashboard.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--db", default="receipts.db",
                    help="SQLite database path (default: receipts.db)")
    ap.add_argument("--rules", default=None,
                    help="category rules YAML (default: data/categories.yaml)")
    sub = ap.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="OCR and ingest receipt files or folders")
    p_ingest.add_argument("paths", nargs="+", help="receipt file(s) or directory(ies)")
    p_ingest.set_defaults(func=cmd_ingest)

    p_report = sub.add_parser("report", help="monthly spending report + chart")
    p_report.add_argument("--month", required=True, type=parse_month,
                          help="month as YYYY-MM")
    p_report.add_argument("--out", default="reports",
                          help="output directory (default: reports)")
    p_report.set_defaults(func=cmd_report)

    p_cat = sub.add_parser("categories", help="list categories or review queue")
    p_cat.add_argument("--review", action="store_true",
                       help="show uncategorized items needing review")
    p_cat.add_argument("--month", default=None, type=parse_month,
                       help="limit totals to YYYY-MM")
    p_cat.set_defaults(func=cmd_categories)

    p_recat = sub.add_parser("recategorize", help="move one item to a category")
    p_recat.add_argument("item_id", type=int)
    p_recat.add_argument("category")
    p_recat.set_defaults(func=cmd_recategorize)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, ocr.OCRError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
