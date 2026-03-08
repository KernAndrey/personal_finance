"""Chart generation for finance CLI. Outputs PNG files."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from db import CHARTS_DIR

# Dark theme colors
BG_COLOR = "#1a1a2e"
TEXT_COLOR = "#e0e0e0"
GRID_COLOR = "#2a2a4e"

CATEGORY_COLORS = [
    "#e94560", "#0f3460", "#16213e", "#533483",
    "#e76f51", "#2a9d8f", "#e9c46a", "#264653",
    "#f4a261", "#a8dadc", "#457b9d", "#1d3557",
    "#6a4c93",
]


def _setup_style():
    plt.rcParams.update({
        "figure.facecolor": BG_COLOR,
        "axes.facecolor": BG_COLOR,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "text.color": TEXT_COLOR,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "grid.color": GRID_COLOR,
        "font.family": "DejaVu Sans",
        "figure.figsize": (8, 6),
        "figure.dpi": 100,
    })


def _cleanup_old_charts(max_age_days: int = 7):
    """Remove chart files older than max_age_days."""
    if not CHARTS_DIR.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    for f in CHARTS_DIR.glob("*.png"):
        if f.stat().st_mtime < cutoff:
            f.unlink()


def _save(fig, output_path: str) -> str:
    _cleanup_old_charts()
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return output_path


def chart_pie(data: list[dict], title: str, output_path: str) -> str:
    """Pie chart by category.

    data: [{"name": str, "icon": str, "amount_eur": float, "percent": float}, ...]
    """
    _setup_style()
    fig, ax = plt.subplots()

    labels = [f"{d['icon']} {d['name']}" for d in data]
    sizes = [d["amount_eur"] for d in data]
    colors = CATEGORY_COLORS[: len(data)]

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct=lambda p: f"{p:.1f}%\n({p * sum(sizes) / 100:.0f}€)",
        colors=colors,
        textprops={"color": TEXT_COLOR, "fontsize": 9},
        pctdistance=0.75,
        startangle=90,
    )
    for t in autotexts:
        t.set_fontsize(8)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    return _save(fig, output_path)


def chart_bar(data: list[dict], title: str, output_path: str) -> str:
    """Horizontal bar chart by category (sorted by amount).

    data: [{"name": str, "icon": str, "amount_eur": float}, ...]
    """
    _setup_style()
    fig, ax = plt.subplots()

    sorted_data = sorted(data, key=lambda d: d["amount_eur"])
    labels = [f"{d['icon']} {d['name']}" for d in sorted_data]
    values = [d["amount_eur"] for d in sorted_data]
    colors = CATEGORY_COLORS[: len(sorted_data)]

    bars = ax.barh(labels, values, color=colors)

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max(values) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.0f}€",
            va="center",
            color=TEXT_COLOR,
            fontsize=9,
        )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("EUR")
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))
    return _save(fig, output_path)


def chart_trend(data: list[dict], title: str, output_path: str) -> str:
    """Line chart showing monthly trend.

    data: [{"month": "YYYY-MM", "total": float}, ...]
    """
    _setup_style()
    fig, ax = plt.subplots()

    months = [d["month"] for d in data]
    totals = [d["total"] for d in data]

    ax.plot(months, totals, marker="o", color="#e94560", linewidth=2, markersize=8)
    ax.fill_between(months, totals, alpha=0.15, color="#e94560")

    for i, (m, t) in enumerate(zip(months, totals)):
        ax.annotate(
            f"{t:.0f}€",
            (m, t),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=9,
            color=TEXT_COLOR,
        )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("EUR")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45)
    return _save(fig, output_path)


def chart_daily(data: list[dict], title: str, output_path: str) -> str:
    """Daily bar chart for a month.

    data: [{"day": int, "total": float, "is_weekend": bool}, ...]
    """
    _setup_style()
    fig, ax = plt.subplots()

    days = [d["day"] for d in data]
    totals = [d["total"] for d in data]
    colors = ["#e9c46a" if d.get("is_weekend") else "#2a9d8f" for d in data]

    ax.bar(days, totals, color=colors, width=0.8)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("День")
    ax.set_ylabel("EUR")
    ax.set_xticks(days)
    ax.grid(axis="y", alpha=0.3)

    # Legend for weekends
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#2a9d8f", label="Будни"),
        Patch(facecolor="#e9c46a", label="Выходные"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")
    return _save(fig, output_path)


def chart_compare(
    data1: list[dict],
    data2: list[dict],
    labels: tuple[str, str],
    title: str,
    output_path: str,
) -> str:
    """Grouped bar chart comparing two periods.

    data1, data2: [{"name": str, "amount_eur": float}, ...]
    labels: ("2026-02", "2026-03")
    """
    _setup_style()
    fig, ax = plt.subplots()

    # Merge categories from both periods
    all_cats = []
    seen = set()
    for d in data1 + data2:
        if d["name"] not in seen:
            all_cats.append(d["name"])
            seen.add(d["name"])

    map1 = {d["name"]: d["amount_eur"] for d in data1}
    map2 = {d["name"]: d["amount_eur"] for d in data2}

    import numpy as np
    x = np.arange(len(all_cats))
    width = 0.35

    vals1 = [map1.get(c, 0) for c in all_cats]
    vals2 = [map2.get(c, 0) for c in all_cats]

    bars1 = ax.bar(x - width / 2, vals1, width, label=labels[0], color="#2a9d8f")
    bars2 = ax.bar(x + width / 2, vals2, width, label=labels[1], color="#e94560")

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("EUR")
    ax.set_xticks(x)
    ax.set_xticklabels(all_cats, rotation=45, ha="right", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, output_path)
