"""Tests for rates.py — exchange rate fetching and caching."""

import pytest
import db
import rates


class TestGetRate:
    def test_eur_always_one(self, tmp_env):
        assert rates.get_rate("EUR") == 1.0
        assert rates.get_rate("eur") == 1.0

    def test_fetches_and_caches(self, tmp_env, mock_rates):
        rate = rates.get_rate("USD")
        assert rate == 1.10

        # Verify it was cached in the DB
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT rate_to_eur FROM exchange_rates WHERE currency = 'USD'"
            ).fetchone()
            assert row is not None
            assert row["rate_to_eur"] == 1.10
        finally:
            conn.close()

    def test_returns_cached_rate(self, tmp_env, mock_rates):
        # Pre-populate cache
        rates._save_rate("2026-03-08", "GEL", 2.99)

        # Even though mock returns 3.0, cache for this date should win
        rate = rates.get_rate("GEL", date="2026-03-08")
        assert rate == 2.99

    def test_gel_rate(self, tmp_env, mock_rates):
        rate = rates.get_rate("GEL")
        assert rate == 3.0

    def test_uah_rate(self, tmp_env, mock_rates):
        rate = rates.get_rate("UAH")
        assert rate == 40.0

    def test_unknown_currency_fallback_to_last_known(self, tmp_env, monkeypatch):
        """If API returns nothing and no cache for today, use last known."""
        monkeypatch.setattr(rates, "_fetch_rates_from_api", lambda: {})

        # Pre-populate with an old rate
        rates._save_rate("2026-01-01", "XYZ", 5.0)
        rate = rates.get_rate("XYZ", date="2026-03-08")
        assert rate == 5.0

    def test_unknown_currency_no_data_returns_none(self, tmp_env, monkeypatch):
        monkeypatch.setattr(rates, "_fetch_rates_from_api", lambda: {})
        rate = rates.get_rate("XYZ")
        assert rate is None


class TestSaveRate:
    def test_save_and_retrieve(self, tmp_env):
        rates._save_rate("2026-06-15", "USD", 1.12)
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM exchange_rates WHERE date='2026-06-15' AND currency='USD'"
            ).fetchone()
            assert row["rate_to_eur"] == 1.12
            assert row["source"] == "api"
        finally:
            conn.close()

    def test_upsert_overwrites(self, tmp_env):
        rates._save_rate("2026-06-15", "USD", 1.12)
        rates._save_rate("2026-06-15", "USD", 1.15)
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT rate_to_eur FROM exchange_rates WHERE date='2026-06-15' AND currency='USD'"
            ).fetchone()
            assert row["rate_to_eur"] == 1.15
        finally:
            conn.close()


class TestUpdateRates:
    def test_update_all_currencies(self, tmp_env, mock_rates, capsys):
        ok = rates.update_rates("2026-03-08")
        assert ok is True

        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT currency FROM exchange_rates WHERE date='2026-03-08'"
            ).fetchall()
            currencies = {r["currency"] for r in rows}
            assert "USD" in currencies
            assert "GEL" in currencies
            assert "UAH" in currencies
        finally:
            conn.close()

    def test_update_fails_if_no_api(self, tmp_env, monkeypatch):
        monkeypatch.setattr(rates, "_fetch_rates_from_api", lambda: {})
        ok = rates.update_rates()
        assert ok is False


class TestFetchRatesMerging:
    def test_merges_primary_and_fallback(self, tmp_env, monkeypatch):
        """Primary API returns USD, fallback adds GEL."""

        call_count = {"n": 0}

        def _fake_fetch_json(url, timeout=10):
            call_count["n"] += 1
            if "frankfurter" in url:
                return {"rates": {"USD": 1.08}}
            else:
                return {"rates": {"GEL": 3.1, "UAH": 41.0, "USD": 1.07}}

        monkeypatch.setattr(rates, "_fetch_json", _fake_fetch_json)

        result = rates._fetch_rates_from_api()
        # USD from primary, GEL/UAH from fallback
        assert result["USD"] == 1.08  # primary wins
        assert result["GEL"] == 3.1
        assert result["UAH"] == 41.0

    def test_fallback_only_when_primary_fails(self, tmp_env, monkeypatch):
        def _fake_fetch_json(url, timeout=10):
            if "frankfurter" in url:
                raise ConnectionError("down")
            return {"rates": {"USD": 1.09, "GEL": 3.2, "UAH": 42.0}}

        monkeypatch.setattr(rates, "_fetch_json", _fake_fetch_json)

        result = rates._fetch_rates_from_api()
        assert result["USD"] == 1.09
        assert result["GEL"] == 3.2

    def test_both_apis_fail(self, tmp_env, monkeypatch):
        def _fail(url, timeout=10):
            raise ConnectionError("down")

        monkeypatch.setattr(rates, "_fetch_json", _fail)

        result = rates._fetch_rates_from_api()
        assert result == {}
