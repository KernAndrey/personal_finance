"""Tests for db.py — database layer."""

import sqlite3
from datetime import datetime, timezone

import pytest
import db


# ── Migrations ──────────────────────────────────────────────────────────────


class TestMigrations:
    def test_fresh_db_creates_all_tables(self, tmp_env):
        conn = db.get_connection()
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()

        assert "transactions" in tables
        assert "exchange_rates" in tables
        assert "categories" in tables
        assert "schema_version" in tables

    def test_migration_is_idempotent(self, tmp_env):
        """Running migrations twice should not fail."""
        db.ensure_migrated()
        db.ensure_migrated()

        conn = db.get_connection()
        try:
            versions = conn.execute("SELECT version FROM schema_version").fetchall()
        finally:
            conn.close()
        assert len(versions) == 1
        assert versions[0]["version"] == 1

    def test_wal_mode_enabled(self, tmp_env):
        conn = db.get_connection()
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        assert mode == "wal"

    def test_initial_categories_seeded(self, tmp_env):
        cats = db.get_categories()
        names = {c["name"] for c in cats}
        assert "Еда" in names
        assert "Жильё" in names
        assert "Прочее" in names
        assert len(cats) == 13


# ── add_transaction ─────────────────────────────────────────────────────────


class TestAddTransaction:
    def test_add_eur(self, tmp_env):
        tx_id = db.add_transaction(
            amount=30.0, currency="EUR", category="Еда",
            description="обед", exchange_rate=1.0, amount_eur=30.0,
        )
        assert tx_id == 1

        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 30.0
        assert tx["currency"] == "EUR"
        assert tx["amount_eur"] == 30.0
        assert tx["exchange_rate"] == 1.0
        assert tx["category"] == "Еда"
        assert tx["description"] == "обед"
        assert tx["source"] == "manual"

    def test_add_non_eur_with_precalculated_rate(self, tmp_env):
        tx_id = db.add_transaction(
            amount=90.0, currency="GEL", category="Транспорт",
            exchange_rate=3.0, amount_eur=30.0,
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 90.0
        assert tx["currency"] == "GEL"
        assert tx["amount_eur"] == 30.0
        assert tx["exchange_rate"] == 3.0

    def test_add_auto_dt(self, tmp_env):
        tx_id = db.add_transaction(
            amount=10.0, currency="EUR", category="Прочее",
            exchange_rate=1.0, amount_eur=10.0,
        )
        tx = db.get_transaction_by_id(tx_id)
        # dt should be set automatically as ISO 8601
        assert tx["dt"] is not None
        assert "T" in tx["dt"]

    def test_add_custom_dt(self, tmp_env):
        tx_id = db.add_transaction(
            amount=10.0, currency="EUR", category="Прочее",
            dt="2025-12-25T10:00:00",
            exchange_rate=1.0, amount_eur=10.0,
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["dt"] == "2025-12-25T10:00:00"

    def test_add_all_optional_fields(self, tmp_env):
        tx_id = db.add_transaction(
            amount=100.0, currency="EUR", category="Еда",
            description="ужин", dt="2026-03-08T20:00:00",
            subcategory="ресторан", receipt_path="receipts/2026-03/photo.jpg",
            source="telegram", tags='["food", "dinner"]',
            exchange_rate=1.0, amount_eur=100.0,
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["subcategory"] == "ресторан"
        assert tx["receipt_path"] == "receipts/2026-03/photo.jpg"
        assert tx["source"] == "telegram"
        assert tx["tags"] == '["food", "dinner"]'

    def test_add_eur_auto_sets_rate(self, tmp_env):
        """When currency=EUR, amount_eur and exchange_rate should be set
        automatically even if not provided."""
        tx_id = db.add_transaction(
            amount=55.0, currency="EUR", category="Прочее",
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount_eur"] == 55.0
        assert tx["exchange_rate"] == 1.0

    def test_add_zero_amount(self, tmp_env):
        tx_id = db.add_transaction(
            amount=0.0, currency="EUR", category="Прочее",
            exchange_rate=1.0, amount_eur=0.0,
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 0.0

    def test_add_large_amount(self, tmp_env):
        tx_id = db.add_transaction(
            amount=999999.99, currency="EUR", category="Бизнес",
            exchange_rate=1.0, amount_eur=999999.99,
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 999999.99

    def test_add_unicode_description(self, tmp_env):
        desc = "Кафе «Мечта» — завтрак 🥐"
        tx_id = db.add_transaction(
            amount=12.0, currency="EUR", category="Еда",
            description=desc, exchange_rate=1.0, amount_eur=12.0,
        )
        tx = db.get_transaction_by_id(tx_id)
        assert tx["description"] == desc


# ── get_transactions ────────────────────────────────────────────────────────


class TestGetTransactions:
    def test_empty_db(self, tmp_env):
        assert db.get_transactions() == []

    def test_no_filters(self, sample_transactions):
        txs = db.get_transactions()
        assert len(txs) == 5

    def test_filter_by_month(self, sample_transactions):
        txs = db.get_transactions(month="2026-03")
        assert len(txs) == 4  # excludes Feb record

    def test_filter_by_category(self, sample_transactions):
        txs = db.get_transactions(category="Еда")
        assert len(txs) == 2

    def test_filter_by_currency(self, sample_transactions):
        txs = db.get_transactions(currency="GEL")
        assert len(txs) == 1
        assert txs[0]["currency"] == "GEL"

    def test_combined_filters(self, sample_transactions):
        txs = db.get_transactions(month="2026-03", category="Еда")
        assert len(txs) == 2

    def test_limit(self, sample_transactions):
        txs = db.get_transactions(limit=2)
        assert len(txs) == 2

    def test_ordered_by_dt_desc(self, sample_transactions):
        txs = db.get_transactions()
        dates = [tx["dt"] for tx in txs]
        assert dates == sorted(dates, reverse=True)


# ── get_transactions_for_period ─────────────────────────────────────────────


class TestGetTransactionsForPeriod:
    def test_by_month(self, sample_transactions):
        txs = db.get_transactions_for_period("2026-03")
        assert len(txs) == 4

    def test_by_month_empty(self, sample_transactions):
        txs = db.get_transactions_for_period("2025-01")
        assert len(txs) == 0

    def test_by_quarter(self, sample_transactions):
        # Q1 2026 = Jan-Mar
        txs = db.get_transactions_for_period("2026-Q1")
        assert len(txs) == 5  # all 5 records are in Q1

    def test_by_quarter_q2_empty(self, sample_transactions):
        txs = db.get_transactions_for_period("2026-Q2")
        assert len(txs) == 0

    def test_by_year(self, sample_transactions):
        txs = db.get_transactions_for_period("2026")
        assert len(txs) == 5

    def test_by_year_wrong(self, sample_transactions):
        txs = db.get_transactions_for_period("2025")
        assert len(txs) == 0

    def test_with_category_filter(self, sample_transactions):
        txs = db.get_transactions_for_period("2026-03", category="Еда")
        assert len(txs) == 2

    def test_with_currency_filter(self, sample_transactions):
        txs = db.get_transactions_for_period("2026-03", currency="GEL")
        assert len(txs) == 1

    def test_quarter_case_insensitive(self, sample_transactions):
        txs = db.get_transactions_for_period("2026-q1")
        assert len(txs) == 5


# ── update_transaction ──────────────────────────────────────────────────────


class TestUpdateTransaction:
    def test_update_amount(self, sample_transactions):
        tx_id = sample_transactions[0]
        ok = db.update_transaction(tx_id, amount=35.0, amount_eur=35.0)
        assert ok is True
        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 35.0
        assert tx["amount_eur"] == 35.0

    def test_update_category(self, sample_transactions):
        tx_id = sample_transactions[0]
        ok = db.update_transaction(tx_id, category="Развлечения")
        assert ok is True
        tx = db.get_transaction_by_id(tx_id)
        assert tx["category"] == "Развлечения"

    def test_update_description(self, sample_transactions):
        tx_id = sample_transactions[0]
        db.update_transaction(tx_id, description="новое описание")
        tx = db.get_transaction_by_id(tx_id)
        assert tx["description"] == "новое описание"

    def test_update_sets_updated_at(self, sample_transactions):
        tx_id = sample_transactions[0]
        tx_before = db.get_transaction_by_id(tx_id)
        db.update_transaction(tx_id, description="changed")
        tx_after = db.get_transaction_by_id(tx_id)
        assert tx_after["updated_at"] != tx_before["updated_at"]

    def test_update_no_valid_fields_returns_false(self, sample_transactions):
        tx_id = sample_transactions[0]
        ok = db.update_transaction(tx_id, bogus_field="nope")
        assert ok is False

    def test_update_none_values_ignored(self, sample_transactions):
        tx_id = sample_transactions[0]
        ok = db.update_transaction(tx_id, amount=None, category=None)
        assert ok is False

    def test_update_nonexistent_id(self, tmp_env):
        ok = db.update_transaction(9999, amount=10.0)
        assert ok is False

    def test_update_multiple_fields(self, sample_transactions):
        tx_id = sample_transactions[0]
        db.update_transaction(tx_id, amount=99.0, description="update test", tags='["new"]')
        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 99.0
        assert tx["description"] == "update test"
        assert tx["tags"] == '["new"]'

    def test_disallowed_field_filtered(self, sample_transactions):
        """Fields not in the allowed set should be silently ignored."""
        tx_id = sample_transactions[0]
        ok = db.update_transaction(tx_id, id=999, created_at="hacked")
        assert ok is False  # no valid fields


# ── delete_transaction ──────────────────────────────────────────────────────


class TestDeleteTransaction:
    def test_delete_existing(self, sample_transactions):
        tx_id = sample_transactions[0]
        ok = db.delete_transaction(tx_id)
        assert ok is True
        assert db.get_transaction_by_id(tx_id) is None

    def test_delete_nonexistent(self, tmp_env):
        ok = db.delete_transaction(9999)
        assert ok is False

    def test_delete_removes_only_target(self, sample_transactions):
        db.delete_transaction(sample_transactions[0])
        remaining = db.get_transactions()
        assert len(remaining) == 4
        remaining_ids = {tx["id"] for tx in remaining}
        assert sample_transactions[0] not in remaining_ids


# ── get_transaction_by_id ───────────────────────────────────────────────────


class TestGetTransactionById:
    def test_existing(self, sample_transactions):
        tx = db.get_transaction_by_id(sample_transactions[0])
        assert tx is not None
        assert tx["id"] == sample_transactions[0]

    def test_nonexistent(self, tmp_env):
        assert db.get_transaction_by_id(9999) is None


# ── get_summary ─────────────────────────────────────────────────────────────


class TestGetSummary:
    def test_summary_structure(self, sample_transactions):
        s = db.get_summary("2026-03")
        assert "period" in s
        assert "categories" in s
        assert "total" in s
        assert "count" in s
        assert "avg_per_day" in s
        assert s["period"] == "2026-03"

    def test_summary_totals(self, sample_transactions):
        s = db.get_summary("2026-03")
        # March: 30 EUR (Еда) + 20 EUR (Транспорт) + 800 EUR (Жильё) + 50 EUR (Еда) = 900
        assert s["total"] == 900.0
        assert s["count"] == 4

    def test_summary_category_breakdown(self, sample_transactions):
        s = db.get_summary("2026-03")
        cats = {c["name"]: c for c in s["categories"]}
        assert cats["Жильё"]["amount_eur"] == 800.0
        assert cats["Еда"]["amount_eur"] == 80.0
        assert cats["Еда"]["count"] == 2
        assert cats["Транспорт"]["amount_eur"] == 20.0

    def test_summary_percentages_add_up(self, sample_transactions):
        s = db.get_summary("2026-03")
        total_pct = sum(c["percent"] for c in s["categories"])
        assert abs(total_pct - 100.0) < 0.5  # rounding tolerance

    def test_summary_sorted_by_amount_desc(self, sample_transactions):
        s = db.get_summary("2026-03")
        amounts = [c["amount_eur"] for c in s["categories"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_summary_empty_period(self, tmp_env):
        s = db.get_summary("2020-01")
        assert s["total"] == 0
        assert s["count"] == 0
        assert s["categories"] == []

    def test_summary_has_icons(self, sample_transactions):
        s = db.get_summary("2026-03")
        for cat in s["categories"]:
            assert cat["icon"] != ""

    def test_summary_quarter(self, sample_transactions):
        s = db.get_summary("2026-Q1")
        # All 5 records: 30+20+800+15+50 = 915
        assert s["total"] == 915.0
        assert s["count"] == 5

    def test_summary_year(self, sample_transactions):
        s = db.get_summary("2026")
        assert s["total"] == 915.0


# ── get_monthly_totals ──────────────────────────────────────────────────────


class TestGetMonthlyTotals:
    def test_returns_correct_count(self, tmp_env):
        result = db.get_monthly_totals(6)
        assert len(result) == 6

    def test_months_in_order(self, tmp_env):
        result = db.get_monthly_totals(3)
        months = [r["month"] for r in result]
        assert months == sorted(months)

    def test_totals_with_data(self, sample_transactions):
        result = db.get_monthly_totals(6)
        # Find March 2026
        march = next((r for r in result if r["month"] == "2026-03"), None)
        if march:
            assert march["total"] == 900.0
            assert march["count"] == 4


# ── get_categories / validate_category ──────────────────────────────────────


class TestCategories:
    def test_get_categories_returns_all(self, tmp_env):
        cats = db.get_categories()
        assert len(cats) == 13

    def test_categories_sorted_by_sort_order(self, tmp_env):
        cats = db.get_categories()
        orders = [c["sort_order"] for c in cats]
        assert orders == sorted(orders)

    def test_validate_existing_category(self, tmp_env):
        assert db.validate_category("Еда") is True
        assert db.validate_category("Жильё") is True

    def test_validate_nonexistent_category(self, tmp_env):
        assert db.validate_category("НесуществующаяКатегория") is False
        assert db.validate_category("") is False

    def test_category_has_icon(self, tmp_env):
        cats = db.get_categories()
        for c in cats:
            assert c["icon"] is not None
            assert len(c["icon"]) > 0


# ── _days_in_period ─────────────────────────────────────────────────────────


class TestDaysInPeriod:
    def test_past_month(self):
        assert db._days_in_period("2026-01") == 31
        assert db._days_in_period("2026-02") == 28
        assert db._days_in_period("2024-02") == 29  # leap year

    def test_past_year(self):
        assert db._days_in_period("2025") == 365
        assert db._days_in_period("2024") == 366  # leap year

    def test_past_quarter(self):
        # Q1 2025 = Jan(31) + Feb(28) + Mar(31) = 90
        assert db._days_in_period("2025-Q1") == 90
