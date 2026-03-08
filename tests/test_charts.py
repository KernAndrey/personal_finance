"""Tests for charts.py — chart generation."""

import os
import time
from pathlib import Path

import pytest

import db


class TestChartGeneration:
    def test_pie_chart(self, tmp_env):
        import charts

        data = [
            {"name": "Еда", "icon": "🍽️", "amount_eur": 200.0, "percent": 66.7},
            {"name": "Транспорт", "icon": "🚗", "amount_eur": 100.0, "percent": 33.3},
        ]
        out = str(tmp_env.charts_dir / "test_pie.png")
        result = charts.chart_pie(data, "Test Pie", out)
        assert result == out
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_bar_chart(self, tmp_env):
        import charts

        data = [
            {"name": "Еда", "icon": "🍽️", "amount_eur": 200.0},
            {"name": "Транспорт", "icon": "🚗", "amount_eur": 100.0},
            {"name": "Жильё", "icon": "🏠", "amount_eur": 800.0},
        ]
        out = str(tmp_env.charts_dir / "test_bar.png")
        result = charts.chart_bar(data, "Test Bar", out)
        assert os.path.isfile(result)

    def test_trend_chart(self, tmp_env):
        import charts

        data = [
            {"month": "2026-01", "total": 500.0},
            {"month": "2026-02", "total": 650.0},
            {"month": "2026-03", "total": 800.0},
        ]
        out = str(tmp_env.charts_dir / "test_trend.png")
        result = charts.chart_trend(data, "Test Trend", out)
        assert os.path.isfile(result)

    def test_daily_chart(self, tmp_env):
        import charts

        data = [
            {"day": 1, "total": 30.0, "is_weekend": False},
            {"day": 2, "total": 0.0, "is_weekend": False},
            {"day": 3, "total": 50.0, "is_weekend": True},
        ]
        out = str(tmp_env.charts_dir / "test_daily.png")
        result = charts.chart_daily(data, "Test Daily", out)
        assert os.path.isfile(result)

    def test_compare_chart(self, tmp_env):
        import charts

        d1 = [
            {"name": "Еда", "amount_eur": 200.0},
            {"name": "Транспорт", "amount_eur": 50.0},
        ]
        d2 = [
            {"name": "Еда", "amount_eur": 300.0},
            {"name": "Жильё", "amount_eur": 800.0},
        ]
        out = str(tmp_env.charts_dir / "test_compare.png")
        result = charts.chart_compare(d1, d2, ("Feb", "Mar"), "Test Compare", out)
        assert os.path.isfile(result)

    def test_single_category_pie(self, tmp_env):
        import charts

        data = [{"name": "Еда", "icon": "🍽️", "amount_eur": 100.0, "percent": 100.0}]
        out = str(tmp_env.charts_dir / "test_single_pie.png")
        result = charts.chart_pie(data, "Single", out)
        assert os.path.isfile(result)

    def test_all_zero_daily(self, tmp_env):
        import charts

        data = [{"day": i, "total": 0.0, "is_weekend": False} for i in range(1, 4)]
        out = str(tmp_env.charts_dir / "test_zero_daily.png")
        result = charts.chart_daily(data, "Zero", out)
        assert os.path.isfile(result)


class TestChartCleanup:
    def test_cleanup_removes_old_files(self, tmp_env):
        import charts

        old_file = tmp_env.charts_dir / "old_chart.png"
        old_file.write_text("fake")
        # Set mtime to 10 days ago
        old_mtime = time.time() - 10 * 86400
        os.utime(old_file, (old_mtime, old_mtime))

        new_file = tmp_env.charts_dir / "new_chart.png"
        new_file.write_text("fake")

        charts._cleanup_old_charts(max_age_days=7)

        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_keeps_recent_files(self, tmp_env):
        import charts

        recent = tmp_env.charts_dir / "recent.png"
        recent.write_text("fake")

        charts._cleanup_old_charts(max_age_days=7)
        assert recent.exists()
