"""
Minimal unit tests for the parts of FORESIGHT that are pure functions —
the risk-scoring rules and the WAPE metric. Run with:

    pytest tests/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from forecast import wape, seasonal_naive_forecast  # noqa: E402
from risk import score_stockout_risk, score_overstock_risk, quadrant  # noqa: E402
import numpy as np


def test_wape_perfect_forecast_is_zero():
    y = [10, 20, 30]
    assert wape(y, y) == 0.0


def test_wape_penalizes_error_proportionally():
    y_true = [10, 10, 10, 10]
    y_pred = [12, 8, 10, 10]
    assert abs(wape(y_true, y_pred) - (2 + 2) / 40) < 1e-9


def test_seasonal_naive_repeats_last_season():
    import pandas as pd
    history = pd.Series([1, 2, 3, 4, 5, 6, 7])  # one week
    fc = seasonal_naive_forecast(history, horizon=7, season_length=7)
    assert list(fc) == [1, 2, 3, 4, 5, 6, 7]


def test_stockout_risk_zero_when_amply_stocked():
    r = score_stockout_risk(forecast_over_lead_time=50, on_hand=200, on_order=0)
    assert r == 0.0


def test_stockout_risk_high_when_undersupplied():
    r = score_stockout_risk(forecast_over_lead_time=100, on_hand=5, on_order=0)
    assert r > 0.9


def test_overstock_risk_zero_when_demand_matches_stock():
    r = score_overstock_risk(on_hand=50, forecast_over_window=50)
    assert r == 0.0


def test_overstock_risk_high_when_stock_far_exceeds_demand():
    r = score_overstock_risk(on_hand=500, forecast_over_window=10)
    assert r > 0.9


def test_quadrant_mapping():
    assert quadrant(0.8, 0.1)[0] == "Reorder now"
    assert quadrant(0.1, 0.8)[0] == "Markdown / clear"
    assert quadrant(0.8, 0.8)[0] == "Watch / volatile"
    assert quadrant(0.1, 0.1)[0] == "Healthy"
