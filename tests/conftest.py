"""Shared fixtures for personal_finance tests."""

import os
import sys
import shutil
from pathlib import Path

import pytest

# Add project root to path so we can import modules
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Redirect all DB/data paths to a temp directory and run migrations.

    Yields a namespace with all useful paths.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    receipts_dir = data_dir / "receipts"
    receipts_dir.mkdir()
    charts_dir = data_dir / "charts"
    charts_dir.mkdir()
    db_path = data_dir / "finance.db"
    migrations_dir = PROJECT_DIR / "migrations"

    import db
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "RECEIPTS_DIR", receipts_dir)
    monkeypatch.setattr(db, "CHARTS_DIR", charts_dir)
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations_dir)

    # Also patch charts and fin modules if imported
    try:
        import charts
        monkeypatch.setattr(charts, "CHARTS_DIR", charts_dir)
    except ImportError:
        pass

    try:
        import fin
        monkeypatch.setattr(fin, "RECEIPTS_DIR", receipts_dir)
        monkeypatch.setattr(fin, "CHARTS_DIR", charts_dir)
    except ImportError:
        pass

    db.ensure_migrated()

    class Env:
        pass

    env = Env()
    env.data_dir = data_dir
    env.db_path = db_path
    env.receipts_dir = receipts_dir
    env.charts_dir = charts_dir
    env.migrations_dir = migrations_dir
    return env


@pytest.fixture()
def mock_rates(monkeypatch):
    """Mock exchange rate API calls to avoid network access.

    Returns a dict that can be mutated to change returned rates.
    """
    import rates

    fake_rates = {"USD": 1.10, "GEL": 3.0, "UAH": 40.0}

    def _fake_fetch_rates():
        return dict(fake_rates)

    monkeypatch.setattr(rates, "_fetch_rates_from_api", _fake_fetch_rates)
    return fake_rates


@pytest.fixture()
def sample_transactions(tmp_env, mock_rates):
    """Insert a set of sample transactions and return their IDs."""
    import db

    ids = []
    ids.append(db.add_transaction(
        amount=30.0, currency="EUR", category="Еда",
        description="обед", dt="2026-03-01T12:00:00",
        exchange_rate=1.0, amount_eur=30.0,
    ))
    ids.append(db.add_transaction(
        amount=60.0, currency="GEL", category="Транспорт",
        description="такси", dt="2026-03-02T08:00:00",
        exchange_rate=3.0, amount_eur=20.0,
    ))
    ids.append(db.add_transaction(
        amount=800.0, currency="EUR", category="Жильё",
        description="аренда", dt="2026-03-01T10:00:00",
        exchange_rate=1.0, amount_eur=800.0,
    ))
    ids.append(db.add_transaction(
        amount=15.0, currency="EUR", category="Подписки",
        description="Netflix", dt="2026-02-15T10:00:00",
        exchange_rate=1.0, amount_eur=15.0,
    ))
    ids.append(db.add_transaction(
        amount=50.0, currency="EUR", category="Еда",
        description="продукты", dt="2026-03-05T18:00:00",
        exchange_rate=1.0, amount_eur=50.0,
    ))
    return ids
