"""Tests for fin.py — CLI commands via click CliRunner."""

import csv
import json
import os
import sys
from io import StringIO
from pathlib import Path

import pytest
from click.testing import CliRunner

import db

# Import cli after path is set by conftest
from fin import cli


@pytest.fixture()
def runner():
    return CliRunner(mix_stderr=False)


# ── add command ─────────────────────────────────────────────────────────────


class TestAddCommand:
    def test_add_eur(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "30", "EUR", "Еда", "обед"])
        assert result.exit_code == 0
        assert "30.00 EUR" in result.output
        assert "Еда" in result.output
        assert "обед" in result.output
        assert "#1" in result.output

    def test_add_non_eur_shows_conversion(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "60", "GEL", "Транспорт", "такси"])
        assert result.exit_code == 0
        assert "60.00 GEL" in result.output
        assert "20.00 EUR" in result.output  # 60 / 3.0

    def test_add_invalid_category(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "10", "EUR", "НетТакой", "test"])
        assert result.exit_code == 1
        assert "Unknown category" in result.stderr

    def test_add_invalid_currency(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "10", "BTC", "Еда", "test"])
        assert result.exit_code != 0

    def test_add_without_description(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "25", "EUR", "Прочее"])
        assert result.exit_code == 0
        assert "25.00 EUR" in result.output

    def test_add_with_custom_dt(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, [
            "add", "10", "EUR", "Еда", "завтрак",
            "--dt", "2026-01-15T08:00:00"
        ])
        assert result.exit_code == 0

        tx = db.get_transaction_by_id(1)
        assert tx["dt"] == "2026-01-15T08:00:00"

    def test_add_with_subcategory(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, [
            "add", "20", "EUR", "Еда", "пицца", "--sub", "доставка"
        ])
        assert result.exit_code == 0
        tx = db.get_transaction_by_id(1)
        assert tx["subcategory"] == "доставка"

    def test_add_with_source(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, [
            "add", "20", "EUR", "Еда", "test", "--source", "telegram"
        ])
        assert result.exit_code == 0
        tx = db.get_transaction_by_id(1)
        assert tx["source"] == "telegram"

    def test_add_with_tags(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, [
            "add", "20", "EUR", "Еда", "test", "--tags", '["food", "lunch"]'
        ])
        assert result.exit_code == 0
        tx = db.get_transaction_by_id(1)
        assert json.loads(tx["tags"]) == ["food", "lunch"]

    def test_add_with_receipt(self, tmp_env, mock_rates, runner, tmp_path):
        receipt = tmp_path / "receipt.jpg"
        receipt.write_text("fake image data")

        result = runner.invoke(cli, [
            "add", "45", "EUR", "Еда", "ужин",
            "--receipt", str(receipt)
        ])
        assert result.exit_code == 0

        tx = db.get_transaction_by_id(1)
        assert tx["receipt_path"] is not None
        assert "receipt.jpg" in tx["receipt_path"]

        # Verify file was actually copied
        full_path = tmp_env.data_dir / tx["receipt_path"]
        assert full_path.exists()

    def test_add_currency_case_insensitive(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "10", "eur", "Еда", "test"])
        assert result.exit_code == 0
        assert "EUR" in result.output

    def test_add_float_amount(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["add", "15.99", "EUR", "Подписки", "Netflix"])
        assert result.exit_code == 0
        assert "15.99" in result.output

    def test_add_negative_amount(self, tmp_env, mock_rates, runner):
        """CLI accepts negative amounts (could represent refunds)."""
        result = runner.invoke(cli, ["add", "--", "-10", "EUR", "Еда", "возврат"])
        assert result.exit_code == 0


# ── last command ────────────────────────────────────────────────────────────


class TestLastCommand:
    def test_empty_db(self, tmp_env, runner):
        result = runner.invoke(cli, ["last"])
        assert result.exit_code == 0
        assert "No transactions" in result.output

    def test_shows_records(self, sample_transactions, runner):
        result = runner.invoke(cli, ["last"])
        assert result.exit_code == 0
        assert "обед" in result.output
        assert "такси" in result.output
        assert "аренда" in result.output

    def test_limit(self, sample_transactions, runner):
        result = runner.invoke(cli, ["last", "2"])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip() and not l.startswith("-") and "ID" not in l]
        assert len(lines) == 2

    def test_json_output(self, sample_transactions, runner):
        result = runner.invoke(cli, ["last", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 5

    def test_json_output_with_limit(self, sample_transactions, runner):
        result = runner.invoke(cli, ["last", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ── show command ────────────────────────────────────────────────────────────


class TestShowCommand:
    def test_by_month(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2026-03"])
        assert result.exit_code == 0
        assert "TOTAL" in result.output
        assert "4 records" in result.output

    def test_empty_period(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2020-01"])
        assert result.exit_code == 0
        assert "No transactions" in result.output

    def test_with_category_filter(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2026-03", "--category", "Еда"])
        assert result.exit_code == 0
        assert "2 records" in result.output

    def test_with_currency_filter(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2026-03", "--currency", "GEL"])
        assert result.exit_code == 0
        assert "1 records" in result.output

    def test_json_output(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2026-03", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4

    def test_by_quarter(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2026-Q1"])
        assert result.exit_code == 0
        assert "5 records" in result.output

    def test_by_year(self, sample_transactions, runner):
        result = runner.invoke(cli, ["show", "2026"])
        assert result.exit_code == 0
        assert "5 records" in result.output


# ── summary command ─────────────────────────────────────────────────────────


class TestSummaryCommand:
    def test_current_month_default(self, tmp_env, mock_rates, runner):
        # Add a record for the current month
        from datetime import datetime, timezone
        now_dt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        runner.invoke(cli, ["add", "50", "EUR", "Еда", "test"])
        result = runner.invoke(cli, ["summary"])
        assert result.exit_code == 0
        assert "ИТОГО" in result.output

    def test_specific_month(self, sample_transactions, runner):
        result = runner.invoke(cli, ["summary", "2026-03"])
        assert result.exit_code == 0
        assert "Расходы за 2026-03" in result.output
        assert "ИТОГО" in result.output
        assert "900.00" in result.output

    def test_empty_period(self, tmp_env, runner):
        result = runner.invoke(cli, ["summary", "2020-01"])
        assert result.exit_code == 0
        assert "No transactions" in result.output

    def test_json_output(self, sample_transactions, runner):
        result = runner.invoke(cli, ["summary", "2026-03", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 900.0
        assert data["count"] == 4
        assert len(data["categories"]) == 3  # Еда, Транспорт, Жильё

    def test_avg_per_day(self, sample_transactions, runner):
        result = runner.invoke(cli, ["summary", "2026-03", "--json"])
        data = json.loads(result.output)
        assert data["avg_per_day"] > 0


# ── compare command ─────────────────────────────────────────────────────────


class TestCompareCommand:
    def test_compare_two_months(self, sample_transactions, runner):
        result = runner.invoke(cli, ["compare", "2026-02", "2026-03"])
        assert result.exit_code == 0
        assert "Сравнение" in result.output
        assert "2026-02" in result.output
        assert "2026-03" in result.output
        assert "ИТОГО" in result.output

    def test_compare_json(self, sample_transactions, runner):
        result = runner.invoke(cli, ["compare", "2026-02", "2026-03", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "period1" in data
        assert "period2" in data
        assert data["period1"]["total"] == 15.0
        assert data["period2"]["total"] == 900.0

    def test_compare_empty_periods(self, tmp_env, runner):
        result = runner.invoke(cli, ["compare", "2020-01", "2020-02"])
        assert result.exit_code == 0
        assert "ИТОГО" in result.output


# ── edit command ────────────────────────────────────────────────────────────


class TestEditCommand:
    def test_edit_amount(self, sample_transactions, mock_rates, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["edit", str(tx_id), "--amount", "35"])
        assert result.exit_code == 0
        assert "updated" in result.output
        assert "35.00" in result.output

        tx = db.get_transaction_by_id(tx_id)
        assert tx["amount"] == 35.0
        assert tx["amount_eur"] == 35.0  # recalculated

    def test_edit_category(self, sample_transactions, mock_rates, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["edit", str(tx_id), "--category", "Развлечения"])
        assert result.exit_code == 0
        tx = db.get_transaction_by_id(tx_id)
        assert tx["category"] == "Развлечения"

    def test_edit_description(self, sample_transactions, mock_rates, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["edit", str(tx_id), "--description", "новый обед"])
        assert result.exit_code == 0
        tx = db.get_transaction_by_id(tx_id)
        assert tx["description"] == "новый обед"

    def test_edit_currency_recalculates_eur(self, sample_transactions, mock_rates, runner):
        tx_id = sample_transactions[0]  # 30 EUR
        result = runner.invoke(cli, ["edit", str(tx_id), "--currency", "GEL"])
        assert result.exit_code == 0
        tx = db.get_transaction_by_id(tx_id)
        assert tx["currency"] == "GEL"
        assert tx["exchange_rate"] == 3.0
        assert tx["amount_eur"] == 10.0  # 30 / 3.0

    def test_edit_nonexistent_id(self, tmp_env, runner):
        result = runner.invoke(cli, ["edit", "9999", "--amount", "10"])
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_edit_invalid_category(self, sample_transactions, mock_rates, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["edit", str(tx_id), "--category", "Фейк"])
        assert result.exit_code == 1
        assert "Unknown category" in result.stderr

    def test_edit_nothing_to_update(self, sample_transactions, mock_rates, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["edit", str(tx_id)])
        assert result.exit_code == 0
        assert "Nothing to update" in result.output


# ── delete command ──────────────────────────────────────────────────────────


class TestDeleteCommand:
    def test_delete_with_yes(self, sample_transactions, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["delete", str(tx_id), "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output
        assert db.get_transaction_by_id(tx_id) is None

    def test_delete_without_yes_confirm(self, sample_transactions, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["delete", str(tx_id)], input="y\n")
        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_delete_without_yes_cancel(self, sample_transactions, runner):
        tx_id = sample_transactions[0]
        result = runner.invoke(cli, ["delete", str(tx_id)], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output
        assert db.get_transaction_by_id(tx_id) is not None

    def test_delete_nonexistent(self, tmp_env, runner):
        result = runner.invoke(cli, ["delete", "9999", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_delete_old_record_blocked(self, tmp_env, mock_rates, runner):
        """Records older than 1 hour cannot be deleted without --force."""
        runner.invoke(cli, ["add", "10", "EUR", "Прочее", "old"])
        # Backdate created_at to 2 hours ago
        conn = db.get_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE transactions SET created_at = datetime('now', '-2 hours') WHERE id = 1"
                )
        finally:
            conn.close()

        result = runner.invoke(cli, ["delete", "1", "--yes"])
        assert result.exit_code == 1
        assert "Only records created within the last hour" in result.stderr
        assert db.get_transaction_by_id(1) is not None

    def test_delete_old_record_with_force(self, tmp_env, mock_rates, runner):
        """--force allows deleting old records."""
        runner.invoke(cli, ["add", "10", "EUR", "Прочее", "old"])
        conn = db.get_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE transactions SET created_at = datetime('now', '-2 hours') WHERE id = 1"
                )
        finally:
            conn.close()

        result = runner.invoke(cli, ["delete", "1", "--yes", "--force"])
        assert result.exit_code == 0
        assert "deleted" in result.output
        assert db.get_transaction_by_id(1) is None

    def test_delete_recent_record_no_force_needed(self, tmp_env, mock_rates, runner):
        """Records created just now can be deleted without --force."""
        runner.invoke(cli, ["add", "10", "EUR", "Прочее", "new"])
        result = runner.invoke(cli, ["delete", "1", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output


# ── categories command ──────────────────────────────────────────────────────


class TestCategoriesCommand:
    def test_lists_all(self, tmp_env, runner):
        result = runner.invoke(cli, ["categories"])
        assert result.exit_code == 0
        assert "Еда" in result.output
        assert "Жильё" in result.output
        assert "Прочее" in result.output
        # Count lines with category icons
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 14


# ── export command ──────────────────────────────────────────────────────────


class TestExportCommand:
    def test_csv_export(self, sample_transactions, runner):
        result = runner.invoke(cli, ["export", "2026-03", "--format", "csv"])
        assert result.exit_code == 0
        path = result.output.strip()
        assert path.endswith(".csv")
        assert os.path.isfile(path)

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 4

    def test_json_export(self, sample_transactions, runner):
        result = runner.invoke(cli, ["export", "2026-03", "--format", "json"])
        assert result.exit_code == 0
        path = result.output.strip()
        assert path.endswith(".json")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 4

    def test_export_empty_period(self, tmp_env, runner):
        result = runner.invoke(cli, ["export", "2020-01"])
        assert result.exit_code == 1
        assert "No transactions" in result.stderr

    def test_csv_has_correct_columns(self, sample_transactions, runner):
        result = runner.invoke(cli, ["export", "2026-03", "--format", "csv"])
        path = result.output.strip()

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

        expected_cols = {"id", "dt", "amount", "currency", "amount_eur",
                         "exchange_rate", "category", "subcategory",
                         "description", "source", "tags"}
        assert set(row.keys()) == expected_cols


# ── rates update command ────────────────────────────────────────────────────


class TestRatesCommand:
    def test_rates_update(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["rates", "update"])
        assert result.exit_code == 0
        assert "Rates updated" in result.output

    def test_rates_update_with_date(self, tmp_env, mock_rates, runner):
        result = runner.invoke(cli, ["rates", "update", "--date", "2026-01-15"])
        assert result.exit_code == 0

        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM exchange_rates WHERE date = '2026-01-15'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_rates_update_failure(self, tmp_env, monkeypatch, runner):
        import rates
        monkeypatch.setattr(rates, "_fetch_rates_from_api", lambda: {})
        result = runner.invoke(cli, ["rates", "update"])
        assert result.exit_code == 1


# ── chart command ───────────────────────────────────────────────────────────


class TestChartCommand:
    def test_pie(self, sample_transactions, runner):
        result = runner.invoke(cli, ["chart", "pie", "2026-03"])
        assert result.exit_code == 0
        path = result.output.strip()
        assert path.endswith(".png")
        assert os.path.isfile(path)

    def test_bar(self, sample_transactions, runner):
        result = runner.invoke(cli, ["chart", "bar", "2026-03"])
        assert result.exit_code == 0
        assert result.output.strip().endswith(".png")

    def test_trend(self, sample_transactions, runner):
        result = runner.invoke(cli, ["chart", "trend"])
        assert result.exit_code == 0
        assert result.output.strip().endswith(".png")

    def test_daily(self, sample_transactions, runner):
        result = runner.invoke(cli, ["chart", "daily", "2026-03"])
        assert result.exit_code == 0
        assert result.output.strip().endswith(".png")

    def test_compare(self, sample_transactions, runner):
        result = runner.invoke(cli, ["chart", "compare", "2026-02", "2026-03"])
        assert result.exit_code == 0
        assert result.output.strip().endswith(".png")

    def test_unknown_type(self, tmp_env, runner):
        result = runner.invoke(cli, ["chart", "unknown"])
        assert result.exit_code == 1

    def test_pie_empty_period(self, tmp_env, runner):
        result = runner.invoke(cli, ["chart", "pie", "2020-01"])
        assert result.exit_code == 1

    def test_trend_empty_db(self, tmp_env, runner):
        result = runner.invoke(cli, ["chart", "trend"])
        assert result.exit_code == 1
        assert "No data" in result.stderr

    def test_compare_missing_args(self, tmp_env, runner):
        result = runner.invoke(cli, ["chart", "compare", "2026-03"])
        assert result.exit_code == 1

    def test_trend_custom_months(self, sample_transactions, runner):
        result = runner.invoke(cli, ["chart", "trend", "--months", "3"])
        assert result.exit_code == 0
        assert result.output.strip().endswith(".png")


# ── Edge cases / integration ────────────────────────────────────────────────


class TestEdgeCases:
    def test_full_lifecycle(self, tmp_env, mock_rates, runner):
        """Add → verify → edit → verify → delete → verify."""
        # Add
        result = runner.invoke(cli, ["add", "100", "EUR", "Еда", "ресторан"])
        assert result.exit_code == 0
        assert "#1" in result.output

        # Verify
        result = runner.invoke(cli, ["last", "1", "--json"])
        data = json.loads(result.output)
        assert data[0]["amount"] == 100.0

        # Edit
        result = runner.invoke(cli, ["edit", "1", "--amount", "120", "--description", "ужин"])
        assert result.exit_code == 0

        # Verify edit
        result = runner.invoke(cli, ["last", "1", "--json"])
        data = json.loads(result.output)
        assert data[0]["amount"] == 120.0
        assert data[0]["description"] == "ужин"

        # Delete
        result = runner.invoke(cli, ["delete", "1", "--yes"])
        assert result.exit_code == 0

        # Verify deleted
        result = runner.invoke(cli, ["last"])
        assert "No transactions" in result.output

    def test_multiple_currencies_in_summary(self, tmp_env, mock_rates, runner):
        """Summary should correctly sum EUR equivalents."""
        runner.invoke(cli, ["add", "30", "EUR", "Еда", "обед"])
        runner.invoke(cli, ["add", "90", "GEL", "Еда", "продукты"])  # 90/3=30 EUR
        runner.invoke(cli, ["add", "55", "USD", "Подписки", "сервис"])  # 55/1.1=50 EUR

        result = runner.invoke(cli, ["summary", "--json"])
        data = json.loads(result.output)
        assert data["total"] == 110.0  # 30 + 30 + 50

    def test_sequential_ids(self, tmp_env, mock_rates, runner):
        """Transaction IDs should auto-increment."""
        for i in range(5):
            runner.invoke(cli, ["add", "10", "EUR", "Прочее", f"tx{i}"])

        result = runner.invoke(cli, ["last", "5", "--json"])
        data = json.loads(result.output)
        ids = sorted(d["id"] for d in data)
        assert ids == [1, 2, 3, 4, 5]
