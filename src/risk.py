"""
Project FORESIGHT — D4 Risk scoring & decisioning.

Combines the demand forecast with current inventory position to score
stockout and overstock risk for every SKU, and maps each SKU onto the
four-quadrant decisioning grid from Section 08 of the brief.

The logic is intentionally simple and fully transparent — it must be
explainable to a non-technical operations team, not a black box.
"""
import argparse
import os

import numpy as np
import pandas as pd

STOCKOUT_HIGH = 0.5   # threshold on the [0,1] stockout-risk score
OVERSTOCK_HIGH = 0.5  # threshold on the [0,1] overstock-risk score
OVERSTOCK_WINDOW_DAYS = 28  # forward window used to judge "far more than you'll sell"


def score_stockout_risk(forecast_over_lead_time: float, on_hand: float, on_order: float,
                         safety_factor: float = 1.15) -> float:
    """
    1.0 = certain stockout, 0.0 = comfortably covered.
    Projected coverage = (on_hand + on_order) vs demand expected over the lead time,
    with a safety margin (safety_factor) built in.
    """
    available = on_hand + on_order
    needed = forecast_over_lead_time * safety_factor
    if needed <= 0:
        return 0.0
    shortfall = max(0.0, needed - available)
    return float(np.clip(shortfall / needed, 0, 1))


def score_overstock_risk(on_hand: float, forecast_over_window: float) -> float:
    """
    1.0 = holding far more than will sell in the window, 0.0 = right-sized or under-stocked.
    """
    if on_hand <= 0:
        return 0.0
    excess = max(0.0, on_hand - forecast_over_window)
    return float(np.clip(excess / max(on_hand, 1e-9), 0, 1))


def quadrant(stockout_risk: float, overstock_risk: float) -> tuple[str, str]:
    high_stock_out = stockout_risk >= STOCKOUT_HIGH
    high_overstock = overstock_risk >= OVERSTOCK_HIGH
    if high_stock_out and not high_overstock:
        return "Reorder now", "Raise a replenishment order before stock runs out."
    if high_overstock and not high_stock_out:
        return "Markdown / clear", "Promote or discount to free up capital."
    if high_stock_out and high_overstock:
        return "Watch / volatile", "Demand looks erratic on both signals — investigate manually."
    return "Healthy", "No action needed; leave as is."


def build_risk_table(forecast_df: pd.DataFrame, inventory_latest: pd.DataFrame,
                      sku_master: pd.DataFrame) -> pd.DataFrame:
    """
    forecast_df: output of forecast.forecast_future() — sku_id, date, forecast, ...
    inventory_latest: most recent on_hand/on_order/lead_time/reorder_point per SKU.
    sku_master: for unit_cost/list_price to quantify rupee value at stake.
    """
    rows = []
    for sku_id, g in forecast_df.groupby("sku_id"):
        g = g.sort_values("date")
        inv = inventory_latest[inventory_latest["sku_id"] == sku_id]
        if inv.empty:
            continue
        inv = inv.iloc[0]
        lead_time = int(inv["lead_time_days"])
        on_hand = float(inv["on_hand_units"])
        on_order = float(inv["on_order_units"])

        forecast_over_lead_time = g["forecast"].head(lead_time).sum()
        forecast_over_window = g["forecast"].head(OVERSTOCK_WINDOW_DAYS).sum()

        so_risk = score_stockout_risk(forecast_over_lead_time, on_hand, on_order)
        os_risk = score_overstock_risk(on_hand, forecast_over_window)
        quad, action = quadrant(so_risk, os_risk)

        sku_row = sku_master[sku_master["sku_id"] == sku_id]
        unit_price = float(sku_row["list_price"].iloc[0]) if not sku_row.empty else np.nan
        unit_cost = float(sku_row["unit_cost"].iloc[0]) if not sku_row.empty else np.nan

        sales_at_risk = max(0.0, forecast_over_lead_time - (on_hand + on_order)) * unit_price
        capital_locked = max(0.0, on_hand - forecast_over_window) * unit_cost

        rows.append({
            "sku_id": sku_id,
            "category": sku_row["category"].iloc[0] if not sku_row.empty else None,
            "on_hand_units": on_hand,
            "on_order_units": on_order,
            "lead_time_days": lead_time,
            "forecast_over_lead_time": round(forecast_over_lead_time, 1),
            "forecast_next_28d": round(forecast_over_window, 1),
            "stockout_risk": round(so_risk, 3),
            "overstock_risk": round(os_risk, 3),
            "quadrant": quad,
            "recommended_action": action,
            "sales_at_risk_inr": round(sales_at_risk, 0),
            "capital_locked_inr": round(capital_locked, 0),
        })

    risk_df = pd.DataFrame(rows).sort_values(
        by=["sales_at_risk_inr", "capital_locked_inr"], ascending=False
    )
    return risk_df.reset_index(drop=True)


def run(forecast_path: str, processed_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    forecast_df = pd.read_csv(forecast_path, parse_dates=["date"])
    analysis_df = pd.read_parquet(processed_path)

    sku_master = analysis_df.drop_duplicates(subset="sku_id")[
        ["sku_id", "category", "unit_cost", "list_price"]
    ]
    inventory_latest = (
        analysis_df.sort_values("date")
        .dropna(subset=["on_hand_units"])
        .groupby("sku_id")
        .tail(1)[["sku_id", "on_hand_units", "on_order_units", "lead_time_days", "reorder_point"]]
    )

    risk_df = build_risk_table(forecast_df, inventory_latest, sku_master)
    out_path = os.path.join(out_dir, "risk_scores.csv")
    risk_df.to_csv(out_path, index=False)
    print(f"Wrote {len(risk_df)} SKU risk scores to {out_path}")
    print(risk_df["quadrant"].value_counts())
    return risk_df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast", default="data/processed/forecast.csv")
    ap.add_argument("--processed", default="data/processed/analysis_ready.parquet")
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()
    run(args.forecast, args.processed, args.out)
