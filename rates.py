"""Exchange rate fetching and caching."""

import json
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Inline db imports to avoid circular dependency at module level
DB_PATH = Path.home() / ".openclaw" / "workspace" / "memory" / "finance" / "finance.db"

SUPPORTED_CURRENCIES = ("EUR", "USD", "UAH", "GEL")

PRIMARY_API = "https://api.frankfurter.dev/v1/latest?base=EUR"
FALLBACK_API = "https://open.er-api.com/v6/latest/EUR"


def _fetch_json(url: str, timeout: int = 10) -> dict:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "fin-cli/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_rates_from_api() -> dict:
    """Fetch EUR-based rates. Returns {currency: rate_from_eur}.

    Merges results from both APIs since the primary (Frankfurter) lacks
    some currencies like GEL and UAH that the fallback provides.
    """
    rates = {}
    try:
        data = _fetch_json(PRIMARY_API)
        rates.update(data.get("rates", {}))
    except Exception:
        pass

    # Always try fallback for currencies missing from primary
    missing = [c for c in SUPPORTED_CURRENCIES if c != "EUR" and c not in rates]
    if missing:
        try:
            data = _fetch_json(FALLBACK_API)
            fallback_rates = data.get("rates", {})
            for cur in missing:
                if cur in fallback_rates:
                    rates[cur] = fallback_rates[cur]
        except Exception as e:
            if not rates:
                print(f"Warning: Could not fetch exchange rates: {e}", file=sys.stderr)

    return rates


def get_rate(currency: str, date: str = None) -> float:
    """Get rate of currency to EUR (how many units of currency per 1 EUR).

    For example, if 1 EUR = 3.0 GEL, returns 3.0.
    To convert GEL to EUR: amount_gel / rate = amount_eur.
    """
    currency = currency.upper()
    if currency == "EUR":
        return 1.0

    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check cache
    import db as db_module
    conn = db_module.get_connection()
    try:
        row = conn.execute(
            "SELECT rate_to_eur FROM exchange_rates WHERE date = ? AND currency = ?",
            (date, currency),
        ).fetchone()
        if row:
            return row["rate_to_eur"]
    finally:
        conn.close()

    # Fetch from API
    rates = _fetch_rates_from_api()
    if currency in rates:
        rate = rates[currency]
        _save_rate(date, currency, rate)
        return rate

    # Fallback: use last known rate
    conn = db_module.get_connection()
    try:
        row = conn.execute(
            """SELECT rate_to_eur FROM exchange_rates
               WHERE currency = ? ORDER BY date DESC LIMIT 1""",
            (currency,),
        ).fetchone()
        if row:
            print(
                f"Warning: Using last known rate for {currency}: {row['rate_to_eur']}",
                file=sys.stderr,
            )
            return row["rate_to_eur"]
    finally:
        conn.close()

    print(f"Error: No rate available for {currency}", file=sys.stderr)
    return None


def _save_rate(date: str, currency: str, rate: float, source: str = "api"):
    import db as db_module
    conn = db_module.get_connection()
    try:
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO exchange_rates (date, currency, rate_to_eur, source)
                   VALUES (?, ?, ?, ?)""",
                (date, currency, rate, source),
            )
    finally:
        conn.close()


def update_rates(date: str = None):
    """Update rates for all supported currencies."""
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rates = _fetch_rates_from_api()
    if not rates:
        print("Error: Could not fetch rates from any API", file=sys.stderr)
        return False

    count = 0
    for cur in SUPPORTED_CURRENCIES:
        if cur == "EUR":
            continue
        if cur in rates:
            _save_rate(date, cur, rates[cur])
            count += 1
            print(f"  {cur}/EUR = {rates[cur]:.4f}")
        else:
            print(f"  Warning: {cur} not found in API response", file=sys.stderr)

    return count > 0
