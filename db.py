"""SQLite database layer: connection, migrations, CRUD operations."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = SKILL_DIR / "migrations"
DATA_DIR = Path.home() / ".openclaw" / "workspace" / "memory" / "finance"
DB_PATH = DATA_DIR / "finance.db"
RECEIPTS_DIR = DATA_DIR / "receipts"
CHARTS_DIR = DATA_DIR / "charts"

SUPPORTED_CURRENCIES = ("EUR", "USD", "UAH", "GEL")


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_migrated():
    conn = get_connection()
    try:
        _run_migrations(conn)
    finally:
        conn.close()


def _run_migrations(conn: sqlite3.Connection):
    # Check if schema_version table exists
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    has_version_table = cur.fetchone() is not None

    applied = set()
    if has_version_table:
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
        applied = {row["version"] for row in rows}

    # Collect migration files sorted by number
    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9]*_*.sql"))
    for mf in migration_files:
        version = int(mf.name.split("_", 1)[0])
        if version in applied:
            continue
        sql = mf.read_text(encoding="utf-8")
        with conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (version,),
            )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_transaction(
    amount: float,
    currency: str,
    category: str,
    description: str = None,
    dt: str = None,
    subcategory: str = None,
    receipt_path: str = None,
    source: str = "manual",
    tags: str = None,
    exchange_rate: float = None,
    amount_eur: float = None,
) -> int:
    if dt is None:
        dt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    if currency == "EUR":
        amount_eur = amount
        exchange_rate = 1.0
    elif amount_eur is None or exchange_rate is None:
        # Caller should provide these; import rates inline to avoid circular
        from rates import get_rate
        rate = get_rate(currency)
        exchange_rate = rate
        amount_eur = round(amount / rate, 2) if rate else None

    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO transactions
                   (dt, amount, currency, amount_eur, exchange_rate,
                    category, subcategory, description, receipt_path,
                    source, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dt, amount, currency, amount_eur, exchange_rate,
                    category, subcategory, description, receipt_path,
                    source, tags,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_transactions(month=None, category=None, currency=None, limit=None):
    conn = get_connection()
    try:
        clauses = []
        params = []
        if month:
            clauses.append("substr(dt, 1, 7) = ?")
            params.append(month)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if currency:
            clauses.append("currency = ?")
            params.append(currency)

        sql = "SELECT * FROM transactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY dt DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_transactions_for_period(period: str, category=None, currency=None):
    """Get transactions for YYYY-MM, YYYY-QN, or YYYY."""
    conn = get_connection()
    try:
        clauses = []
        params = []

        if len(period) == 4:
            # Year: YYYY
            clauses.append("substr(dt, 1, 4) = ?")
            params.append(period)
        elif "Q" in period.upper():
            # Quarter: YYYY-QN
            year, q = period.upper().split("-Q")
            q = int(q)
            start_month = (q - 1) * 3 + 1
            end_month = start_month + 2
            clauses.append("substr(dt, 1, 4) = ?")
            params.append(year)
            clauses.append("CAST(substr(dt, 6, 2) AS INTEGER) >= ?")
            params.append(start_month)
            clauses.append("CAST(substr(dt, 6, 2) AS INTEGER) <= ?")
            params.append(end_month)
        else:
            # Month: YYYY-MM
            clauses.append("substr(dt, 1, 7) = ?")
            params.append(period)

        if category:
            clauses.append("category = ?")
            params.append(category)
        if currency:
            clauses.append("currency = ?")
            params.append(currency)

        sql = "SELECT * FROM transactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY dt DESC"

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_transaction(tx_id: int, **fields) -> bool:
    allowed = {
        "amount", "currency", "category", "subcategory",
        "description", "dt", "tags", "amount_eur", "exchange_rate",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False

    updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [tx_id]

    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                f"UPDATE transactions SET {set_clause} WHERE id = ?", values
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def delete_transaction(tx_id: int) -> bool:
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def get_transaction_by_id(tx_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_summary(period: str = None):
    """Return summary grouped by category for a period."""
    if period is None:
        period = datetime.now(timezone.utc).strftime("%Y-%m")

    txs = get_transactions_for_period(period)
    cats = {c["name"]: c["icon"] for c in get_categories()}

    by_cat = {}
    for tx in txs:
        cat = tx["category"]
        if cat not in by_cat:
            by_cat[cat] = {"amount_eur": 0.0, "count": 0, "icon": cats.get(cat, "")}
        by_cat[cat]["amount_eur"] += tx["amount_eur"] or 0
        by_cat[cat]["count"] += 1

    total = sum(v["amount_eur"] for v in by_cat.values())

    # Sort by amount descending
    sorted_cats = sorted(by_cat.items(), key=lambda x: x[1]["amount_eur"], reverse=True)

    # Calculate days in period for average
    days = _days_in_period(period)

    return {
        "period": period,
        "categories": [
            {
                "name": name,
                "icon": data["icon"],
                "amount_eur": round(data["amount_eur"], 2),
                "percent": round(data["amount_eur"] / total * 100, 1) if total else 0,
                "count": data["count"],
            }
            for name, data in sorted_cats
        ],
        "total": round(total, 2),
        "count": sum(v["count"] for v in by_cat.values()),
        "avg_per_day": round(total / days, 2) if days else 0,
        "days": days,
    }


def _days_in_period(period: str) -> int:
    from calendar import monthrange
    now = datetime.now(timezone.utc)

    if len(period) == 4:
        # Year
        year = int(period)
        if year == now.year:
            return (now - datetime(year, 1, 1, tzinfo=timezone.utc)).days or 1
        return 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365
    elif "Q" in period.upper():
        year, q = period.upper().split("-Q")
        year, q = int(year), int(q)
        start_month = (q - 1) * 3 + 1
        total = 0
        for m in range(start_month, start_month + 3):
            total += monthrange(year, m)[1]
        end_of_q = datetime(year, start_month + 2, monthrange(year, start_month + 2)[1], tzinfo=timezone.utc)
        if now < end_of_q:
            start = datetime(year, start_month, 1, tzinfo=timezone.utc)
            return (now - start).days or 1
        return total
    else:
        # Month YYYY-MM
        year, month = int(period[:4]), int(period[5:7])
        _, last_day = monthrange(year, month)
        if year == now.year and month == now.month:
            return now.day
        return last_day


def get_monthly_totals(months: int = 6):
    """Return monthly totals for the last N months."""
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc)
        results = []
        for i in range(months - 1, -1, -1):
            # Calculate month offset
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            ym = f"{y:04d}-{m:02d}"
            row = conn.execute(
                """SELECT COALESCE(SUM(amount_eur), 0) as total,
                          COUNT(*) as count
                   FROM transactions
                   WHERE substr(dt, 1, 7) = ?""",
                (ym,),
            ).fetchone()
            results.append({
                "month": ym,
                "total": round(row["total"], 2),
                "count": row["count"],
            })
        return results
    finally:
        conn.close()


def get_categories():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM categories ORDER BY sort_order"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def validate_category(name: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()
