#!/usr/bin/env python3
"""Personal finance CLI tool."""

import json
import os
import shutil
import sys
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path

import click

# Add skill directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db
from db import RECEIPTS_DIR, CHARTS_DIR, SUPPORTED_CURRENCIES


def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


@click.group()
def cli():
    """Personal finance tracker CLI."""
    db.ensure_migrated()


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("amount", type=float)
@click.argument("currency", type=click.Choice(SUPPORTED_CURRENCIES, case_sensitive=False))
@click.argument("category")
@click.argument("description", required=False, default=None)
@click.option("--dt", default=None, help="Date-time ISO 8601 (default: now)")
@click.option("--sub", default=None, help="Subcategory")
@click.option("--receipt", default=None, type=click.Path(exists=True), help="Path to receipt file")
@click.option("--source", default="manual", help="Source: telegram/voice/manual")
@click.option("--tags", default=None, help="JSON array of tags")
def add(amount, currency, category, description, dt, sub, receipt, source, tags):
    """Add a transaction."""
    currency = currency.upper()

    if not db.validate_category(category):
        cats = [c["name"] for c in db.get_categories()]
        click.echo(f"Error: Unknown category '{category}'. Available: {', '.join(cats)}", err=True)
        sys.exit(1)

    # Handle receipt
    receipt_rel = None
    if receipt:
        receipt_path = Path(receipt)
        month_dir = (dt or _now_str())[:7]
        dest_dir = RECEIPTS_DIR / month_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / receipt_path.name
        shutil.copy2(str(receipt_path), str(dest))
        receipt_rel = f"receipts/{month_dir}/{receipt_path.name}"

    # Get exchange rate
    from rates import get_rate
    if currency == "EUR":
        rate = 1.0
        amount_eur = amount
    else:
        rate = get_rate(currency)
        if rate is None:
            click.echo(f"Error: Could not get exchange rate for {currency}", err=True)
            sys.exit(1)
        amount_eur = round(amount / rate, 2)

    tx_id = db.add_transaction(
        amount=amount,
        currency=currency,
        category=category,
        description=description,
        dt=dt,
        subcategory=sub,
        receipt_path=receipt_rel,
        source=source,
        tags=tags,
        exchange_rate=rate,
        amount_eur=amount_eur,
    )

    if currency == "EUR":
        click.echo(f"\u2705 #{tx_id} | {amount:.2f} EUR | {category} | {description or ''}")
    else:
        click.echo(
            f"\u2705 #{tx_id} | {amount:.2f} {currency} ({amount_eur:.2f} EUR) | {category} | {description or ''}"
        )


# ---------------------------------------------------------------------------
# last
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("n", type=int, default=10)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def last(n, as_json):
    """Show last N transactions."""
    txs = db.get_transactions(limit=n)

    if as_json:
        click.echo(json.dumps(txs, ensure_ascii=False, indent=2))
        return

    if not txs:
        click.echo("No transactions found.")
        return

    # Table header
    click.echo(f"{'ID':>5}  {'Date':10}  {'Amount':>12}  {'EUR':>10}  {'Category':15}  Description")
    click.echo("-" * 75)
    for tx in txs:
        dt_short = tx["dt"][:10] if tx["dt"] else ""
        if tx["currency"] == "EUR":
            amt = f"{tx['amount']:.2f} EUR"
        else:
            amt = f"{tx['amount']:.2f} {tx['currency']}"
        eur = f"{tx['amount_eur']:.2f}" if tx["amount_eur"] else "—"
        desc = tx["description"] or ""
        click.echo(f"{tx['id']:>5}  {dt_short:10}  {amt:>12}  {eur:>10}  {tx['category']:15}  {desc}")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("period")
@click.option("--category", default=None, help="Filter by category")
@click.option("--currency", default=None, help="Filter by currency")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show(period, category, currency, as_json):
    """Show transactions for a period (YYYY-MM, YYYY-QN, or YYYY)."""
    txs = db.get_transactions_for_period(period, category=category, currency=currency)

    if as_json:
        click.echo(json.dumps(txs, ensure_ascii=False, indent=2))
        return

    if not txs:
        click.echo(f"No transactions found for {period}.")
        return

    click.echo(f"{'ID':>5}  {'Date':10}  {'Amount':>12}  {'EUR':>10}  {'Category':15}  Description")
    click.echo("-" * 75)
    for tx in txs:
        dt_short = tx["dt"][:10] if tx["dt"] else ""
        if tx["currency"] == "EUR":
            amt = f"{tx['amount']:.2f} EUR"
        else:
            amt = f"{tx['amount']:.2f} {tx['currency']}"
        eur = f"{tx['amount_eur']:.2f}" if tx["amount_eur"] else "—"
        desc = tx["description"] or ""
        click.echo(f"{tx['id']:>5}  {dt_short:10}  {amt:>12}  {eur:>10}  {tx['category']:15}  {desc}")

    total = sum(tx["amount_eur"] or 0 for tx in txs)
    click.echo("-" * 75)
    click.echo(f"{'':>5}  {'':10}  {'TOTAL':>12}  {total:>10.2f}  ({len(txs)} records)")


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("period", default=None, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def summary(period, as_json):
    """Show expense summary for a period (default: current month)."""
    if period is None:
        period = _current_month()

    data = db.get_summary(period)

    if as_json:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not data["categories"]:
        click.echo(f"No transactions for {period}.")
        return

    click.echo(f"\n\U0001f4ca Расходы за {data['period']}\n")
    click.echo(f"{'Категория':20} {'Сумма (EUR)':>12} {'%':>7}  {'Кол-во':>6}")
    click.echo("\u2500" * 52)
    for cat in data["categories"]:
        name = f"{cat['icon']} {cat['name']}"
        click.echo(f"{name:20} {cat['amount_eur']:>12.2f} {cat['percent']:>6.1f}%  {cat['count']:>6}")
    click.echo("\u2500" * 52)
    click.echo(f"{'ИТОГО':20} {data['total']:>12.2f} {'100.0%':>7}  {data['count']:>6}")
    click.echo(f"\nСредний расход/день: {data['avg_per_day']:.2f} EUR")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("period1")
@click.argument("period2")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def compare(period1, period2, as_json):
    """Compare expenses between two periods."""
    s1 = db.get_summary(period1)
    s2 = db.get_summary(period2)

    if as_json:
        click.echo(json.dumps({"period1": s1, "period2": s2}, ensure_ascii=False, indent=2))
        return

    # Merge categories
    all_cats = {}
    for c in s1["categories"]:
        all_cats[c["name"]] = {"p1": c["amount_eur"], "p2": 0, "icon": c["icon"]}
    for c in s2["categories"]:
        if c["name"] in all_cats:
            all_cats[c["name"]]["p2"] = c["amount_eur"]
        else:
            all_cats[c["name"]] = {"p1": 0, "p2": c["amount_eur"], "icon": c["icon"]}

    click.echo(f"\n\U0001f4ca Сравнение: {period1} vs {period2}\n")
    click.echo(f"{'Категория':20} {period1:>10} {period2:>10} {'Разница':>10} {'%':>8}")
    click.echo("\u2500" * 62)

    for name, vals in sorted(all_cats.items(), key=lambda x: abs(x[1]["p2"] - x[1]["p1"]), reverse=True):
        diff = vals["p2"] - vals["p1"]
        pct = (diff / vals["p1"] * 100) if vals["p1"] else 0
        sign = "+" if diff > 0 else ""
        label = f"{vals['icon']} {name}"
        click.echo(
            f"{label:20} {vals['p1']:>10.2f} {vals['p2']:>10.2f} {sign}{diff:>9.2f} {sign}{pct:>6.1f}%"
        )

    diff_total = s2["total"] - s1["total"]
    pct_total = (diff_total / s1["total"] * 100) if s1["total"] else 0
    sign = "+" if diff_total > 0 else ""
    click.echo("\u2500" * 62)
    click.echo(
        f"{'ИТОГО':20} {s1['total']:>10.2f} {s2['total']:>10.2f} {sign}{diff_total:>9.2f} {sign}{pct_total:>6.1f}%"
    )


# ---------------------------------------------------------------------------
# chart
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("chart_type")
@click.argument("args", nargs=-1)
@click.option("--months", default=6, type=int, help="Number of months for trend")
def chart(chart_type, args, months):
    """Generate a chart (pie, bar, trend, daily, compare)."""
    import charts
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if chart_type == "pie":
        period = args[0] if args else _current_month()
        data = db.get_summary(period)
        if not data["categories"]:
            click.echo(f"No data for {period}.", err=True)
            sys.exit(1)
        out = str(CHARTS_DIR / f"pie_{period}_{ts}.png")
        title = f"Расходы за {period} — {data['total']:.0f} EUR"
        charts.chart_pie(data["categories"], title, out)
        click.echo(out)

    elif chart_type == "bar":
        period = args[0] if args else _current_month()
        data = db.get_summary(period)
        if not data["categories"]:
            click.echo(f"No data for {period}.", err=True)
            sys.exit(1)
        out = str(CHARTS_DIR / f"bar_{period}_{ts}.png")
        title = f"Расходы за {period} — {data['total']:.0f} EUR"
        charts.chart_bar(data["categories"], title, out)
        click.echo(out)

    elif chart_type == "trend":
        data = db.get_monthly_totals(months)
        if not any(d["total"] > 0 for d in data):
            click.echo("No data for trend.", err=True)
            sys.exit(1)
        out = str(CHARTS_DIR / f"trend_{months}m_{ts}.png")
        title = f"Тренд расходов ({months} мес.)"
        charts.chart_trend(data, title, out)
        click.echo(out)

    elif chart_type == "daily":
        period = args[0] if args else _current_month()
        txs = db.get_transactions_for_period(period)
        if not txs:
            click.echo(f"No data for {period}.", err=True)
            sys.exit(1)

        year, month = int(period[:4]), int(period[5:7])
        _, last_day = monthrange(year, month)

        daily = {}
        for tx in txs:
            day = int(tx["dt"][8:10])
            daily[day] = daily.get(day, 0) + (tx["amount_eur"] or 0)

        from datetime import date as dt_date
        chart_data = []
        for d in range(1, last_day + 1):
            wd = dt_date(year, month, d).weekday()
            chart_data.append({
                "day": d,
                "total": round(daily.get(d, 0), 2),
                "is_weekend": wd >= 5,
            })

        total = sum(dd["total"] for dd in chart_data)
        out = str(CHARTS_DIR / f"daily_{period}_{ts}.png")
        title = f"Расходы по дням {period} — {total:.0f} EUR"
        charts.chart_daily(chart_data, title, out)
        click.echo(out)

    elif chart_type == "compare":
        if len(args) < 2:
            click.echo("Usage: fin chart compare <period1> <period2>", err=True)
            sys.exit(1)
        p1, p2 = args[0], args[1]
        s1 = db.get_summary(p1)
        s2 = db.get_summary(p2)
        if not s1["categories"] and not s2["categories"]:
            click.echo("No data for comparison.", err=True)
            sys.exit(1)
        out = str(CHARTS_DIR / f"compare_{p1}_{p2}_{ts}.png")
        title = f"Сравнение: {p1} vs {p2}"
        charts.chart_compare(s1["categories"], s2["categories"], (p1, p2), title, out)
        click.echo(out)

    else:
        click.echo(f"Unknown chart type: {chart_type}. Use: pie, bar, trend, daily, compare", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("tx_id", type=int)
@click.option("--amount", type=float, default=None)
@click.option("--currency", default=None)
@click.option("--category", default=None)
@click.option("--description", default=None)
@click.option("--dt", default=None)
@click.option("--sub", default=None)
@click.option("--tags", default=None)
def edit(tx_id, amount, currency, category, description, dt, sub, tags):
    """Edit a transaction."""
    tx = db.get_transaction_by_id(tx_id)
    if not tx:
        click.echo(f"Error: Transaction #{tx_id} not found.", err=True)
        sys.exit(1)

    if category and not db.validate_category(category):
        cats = [c["name"] for c in db.get_categories()]
        click.echo(f"Error: Unknown category '{category}'. Available: {', '.join(cats)}", err=True)
        sys.exit(1)

    fields = {}
    if amount is not None:
        fields["amount"] = amount
    if currency is not None:
        fields["currency"] = currency.upper()
    if category is not None:
        fields["category"] = category
    if description is not None:
        fields["description"] = description
    if dt is not None:
        fields["dt"] = dt
    if sub is not None:
        fields["subcategory"] = sub
    if tags is not None:
        fields["tags"] = tags

    # Recalculate EUR if amount or currency changed
    new_amount = fields.get("amount", tx["amount"])
    new_currency = fields.get("currency", tx["currency"])
    if "amount" in fields or "currency" in fields:
        if new_currency == "EUR":
            fields["amount_eur"] = new_amount
            fields["exchange_rate"] = 1.0
        else:
            from rates import get_rate
            rate = get_rate(new_currency)
            if rate is None:
                click.echo(f"Error: Could not get rate for {new_currency}", err=True)
                sys.exit(1)
            fields["amount_eur"] = round(new_amount / rate, 2)
            fields["exchange_rate"] = rate

    if db.update_transaction(tx_id, **fields):
        updated = db.get_transaction_by_id(tx_id)
        if updated["currency"] == "EUR":
            click.echo(f"\u2705 #{tx_id} updated | {updated['amount']:.2f} EUR | {updated['category']}")
        else:
            click.echo(
                f"\u2705 #{tx_id} updated | {updated['amount']:.2f} {updated['currency']} "
                f"({updated['amount_eur']:.2f} EUR) | {updated['category']}"
            )
    else:
        click.echo("Nothing to update.")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("tx_id", type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--force", is_flag=True, help="Force delete old records (user-only)")
def delete(tx_id, yes, force):
    """Delete a transaction.

    Only records created within the last hour can be deleted.
    Older records require --force (intended for manual user action only).
    """
    tx = db.get_transaction_by_id(tx_id)
    if not tx:
        click.echo(f"Error: Transaction #{tx_id} not found.", err=True)
        sys.exit(1)

    # Check if the record was created within the last hour
    created = datetime.fromisoformat(tx["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - created
    if age.total_seconds() > 3600 and not force:
        click.echo(
            f"Error: Transaction #{tx_id} was created {_format_age(age)} ago. "
            f"Only records created within the last hour can be deleted. "
            f"Use --force to override (user-only).",
            err=True,
        )
        sys.exit(1)

    if not yes:
        desc = tx["description"] or ""
        click.echo(f"Delete #{tx_id}: {tx['amount']:.2f} {tx['currency']} | {tx['category']} | {desc}?")
        if not click.confirm("Confirm?"):
            click.echo("Cancelled.")
            return

    if db.delete_transaction(tx_id):
        click.echo(f"\U0001f5d1\ufe0f #{tx_id} deleted.")
    else:
        click.echo(f"Error: Could not delete #{tx_id}.", err=True)
        sys.exit(1)


def _format_age(delta):
    """Format timedelta as a human-readable string."""
    total = int(delta.total_seconds())
    if total < 3600:
        return f"{total // 60} min"
    hours = total // 3600
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


# ---------------------------------------------------------------------------
# rates
# ---------------------------------------------------------------------------
@cli.group("rates")
def rates_group():
    """Exchange rate commands."""
    pass


@rates_group.command("update")
@click.option("--date", default=None, help="Date YYYY-MM-DD (default: today)")
def rates_update(date):
    """Update exchange rates."""
    from rates import update_rates
    click.echo("Updating exchange rates...")
    if update_rates(date):
        click.echo("\u2705 Rates updated.")
    else:
        click.echo("Error: Failed to update rates.", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------
@cli.command()
def categories():
    """Show available categories."""
    cats = db.get_categories()
    for c in cats:
        parent_info = f" (-> {c['parent']})" if c.get("parent") else ""
        click.echo(f"  {c['icon']}  {c['name']}{parent_info}")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("period")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv", help="Export format")
def export(period, fmt):
    """Export transactions for a period to CSV or JSON."""
    txs = db.get_transactions_for_period(period)
    if not txs:
        click.echo(f"No transactions for {period}.", err=True)
        sys.exit(1)

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if fmt == "json":
        out_path = CHARTS_DIR / f"export_{period}_{ts}.json"
        out_path.write_text(json.dumps(txs, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        out_path = CHARTS_DIR / f"export_{period}_{ts}.csv"
        import csv
        fields = [
            "id", "dt", "amount", "currency", "amount_eur", "exchange_rate",
            "category", "subcategory", "description", "source", "tags",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(txs)

    click.echo(str(out_path))


if __name__ == "__main__":
    cli()
