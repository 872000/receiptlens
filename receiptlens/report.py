"""Monthly spending reports: terminal tables, Markdown and charts.

Category totals are *tax-inclusive*: each receipt's tax is distributed
across its line items in proportion to their prices, so the category
totals add up to what was actually paid.
"""
from __future__ import annotations

import calendar
import os
from pathlib import Path

from . import categorizer, store

os.environ.setdefault("MPLBACKEND", "Agg")


def _color_for(category: str, rules: list[categorizer.CategoryRule]) -> str:
    for rule in rules:
        if rule.name == category:
            return rule.color
    return categorizer.DEFAULT_COLOR


def _tax_inclusive_factor(receipt: dict, subtotal: float) -> float:
    """Pro-rating factor so category totals add up to what was actually paid.

    Falls back to 1.0 when the receipt has no printed total or no subtotal,
    so category totals gracefully degrade to plain item prices.
    """
    total = receipt["total"]
    if not subtotal or not total:
        return 1.0
    return total / subtotal


def monthly_data(
    conn, year: int, month: int, rules: list[categorizer.CategoryRule]
) -> dict:
    """Aggregate everything the report needs for one calendar month."""
    receipts = store.get_receipts(conn, year, month)

    categories: dict[str, dict] = {}
    merchants: dict[str, float] = {}
    tax_total = 0.0
    grand_total = 0.0
    n_items = 0

    for receipt in receipts:
        items = store.get_items(conn, receipt["id"])
        subtotal = receipt["subtotal"] or sum(i["price"] for i in items)
        factor = _tax_inclusive_factor(receipt, subtotal)
        for item in items:
            bucket = categories.setdefault(
                item["category"], {"total": 0.0, "count": 0}
            )
            bucket["total"] += item["price"] * factor
            bucket["count"] += 1
            n_items += 1
        merchants[receipt["merchant"]] = merchants.get(receipt["merchant"], 0.0) + (
            receipt["total"] or subtotal
        )
        tax_total += receipt["tax"] or 0.0
        grand_total += receipt["total"] or subtotal

    category_rows = [
        {
            "category": name,
            "total": round(data["total"], 2),
            "count": data["count"],
            "share": round(data["total"] / grand_total * 100, 1) if grand_total else 0.0,
            "color": _color_for(name, rules),
        }
        for name, data in categories.items()
    ]
    category_rows.sort(key=lambda r: r["total"], reverse=True)

    merchant_rows = [
        {"merchant": name, "total": round(total, 2)}
        for name, total in sorted(merchants.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "n_receipts": len(receipts),
        "n_items": n_items,
        "grand_total": round(grand_total, 2),
        "tax_total": round(tax_total, 2),
        "categories": category_rows,
        "merchants": merchant_rows,
    }


def print_report(data: dict) -> None:
    """Print the monthly report as a terminal table."""
    title = f"Spending report — {data['month_name']} {data['year']}"
    print(title)
    print("=" * len(title))
    if not data["n_receipts"]:
        print("No receipts ingested for this month yet.")
        return
    print(
        f"Receipts: {data['n_receipts']}   "
        f"Items: {data['n_items']}   "
        f"Total: ${data['grand_total']:.2f}\n"
    )
    print(f"{'Category':<16}{'Items':>7}{'Total':>12}{'Share':>8}")
    print("-" * 45)
    for row in data["categories"]:
        marker = "  <-- review" if row["category"] == categorizer.UNCATEGORIZED else ""
        print(
            f"{row['category']:<16}{row['count']:>7}"
            f"${row['total']:>11.2f}{row['share']:>7.1f}%{marker}"
        )
    print("-" * 45)
    print(f"{'Tax (HST/GST)':<16}{'':>7}${data['tax_total']:>11.2f}")
    print(f"\nTop merchants:")
    for row in data["merchants"][:5]:
        print(f"  {row['merchant']:<28} ${row['total']:.2f}")


def make_chart(data: dict, png_path: str | Path) -> Path:
    """Render the bar + pie spending chart and save it as PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    title = f"Monthly spending — {data['month_name']} {data['year']}"
    fig, (ax_bar, ax_pie) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    if not data["categories"]:
        fig.text(0.5, 0.5, "No spending data for this month",
                 ha="center", va="center", fontsize=12)
    else:
        rows = data["categories"]
        names = [r["category"] for r in rows]
        totals = [r["total"] for r in rows]
        colors = [r["color"] for r in rows]

        bars = ax_bar.barh(names[::-1], totals[::-1], color=colors[::-1])
        ax_bar.set_xlabel("Total ($, incl. tax)")
        ax_bar.set_title("Spending by category")
        ax_bar.bar_label(bars, fmt="$%.2f", padding=3, fontsize=8)

        wedges, _, _ = ax_pie.pie(
            totals,
            colors=colors,
            autopct=lambda p: f"{p:.1f}%" if p >= 4 else "",
            startangle=90,
            textprops={"fontsize": 8},
        )
        ax_pie.legend(
            wedges,
            [f"{n} (${t:.2f})" for n, t in zip(names, totals)],
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            fontsize=8,
            frameon=False,
        )
        ax_pie.set_title("Share of spending")

    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return png_path


def save_report(
    data: dict,
    outdir: str | Path,
    rules: list[categorizer.CategoryRule] | None = None,
) -> tuple[Path, Path]:
    """Write the Markdown report and chart PNG into *outdir*.

    Returns ``(markdown_path, chart_path)``.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = f"{data['year']:04d}-{data['month']:02d}"
    md_path = outdir / f"{stamp}-report.md"
    png_path = outdir / f"{stamp}-spending.png"

    lines = [
        f"# Spending report — {data['month_name']} {data['year']}",
        "",
        f"**Receipts:** {data['n_receipts']} · **Items:** {data['n_items']} · "
        f"**Total:** ${data['grand_total']:.2f} · **Tax:** ${data['tax_total']:.2f}",
        "",
        f"![Monthly spending chart]({png_path.name})",
        "",
        "| Category | Items | Total (incl. tax) | Share |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in data["categories"]:
        lines.append(
            f"| {row['category']} | {row['count']} "
            f"| ${row['total']:.2f} | {row['share']:.1f}% |"
        )
    lines += [
        "",
        "## Top merchants",
        "",
        "| Merchant | Total |",
        "| --- | ---: |",
    ]
    for row in data["merchants"]:
        lines.append(f"| {row['merchant']} | ${row['total']:.2f} |")
    lines += [
        "",
        "_Generated by [ReceiptLens](https://github.com/PARTHPATEL5577/receiptlens)._",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    make_chart(data, png_path)
    return md_path, png_path
