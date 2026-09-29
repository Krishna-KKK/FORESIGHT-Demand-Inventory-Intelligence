"""
Project FORESIGHT — D5 Planning dashboard.

Run with:
    streamlit run app/app.py

Reads the pipeline outputs from data/processed/. If they don't exist yet,
shows a clear empty state with instructions instead of crashing.
"""
import os
import sys

import pandas as pd
import streamlit as st

try:
    import plotly.express as px  # type: ignore[import-not-found]
except ModuleNotFoundError:
    px = None

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

st.set_page_config(page_title="FORESIGHT — Planning Dashboard", layout="wide")

st.title("📦 Project FORESIGHT — Demand & Inventory Planning")
st.caption("NorthBay Living · Forecast, risk, and reorder guidance for the ops team")


@st.cache_data
def load_data():
    analysis_path = os.path.join(DATA_DIR, "analysis_ready.parquet")
    forecast_path = os.path.join(DATA_DIR, "forecast.csv")
    risk_path = os.path.join(DATA_DIR, "risk_scores.csv")
    backtest_path = os.path.join(DATA_DIR, "backtest_summary.json")

    if not all(os.path.exists(p) for p in [analysis_path, forecast_path, risk_path]):
        return None

    analysis_df = pd.read_parquet(analysis_path)
    forecast_df = pd.read_csv(forecast_path, parse_dates=["date"])
    risk_df = pd.read_csv(risk_path)
    backtest = None
    if os.path.exists(backtest_path):
        import json
        with open(backtest_path) as f:
            backtest = json.load(f)
    return analysis_df, forecast_df, risk_df, backtest


data = load_data()

if data is None:
    st.warning(
        "No pipeline output found yet.\n\n"
        "Run these once, from the project root, before opening this dashboard:\n\n"
        "```\n"
        "python data_generator/generate_data.py --out data/raw\n"
        "python src/pipeline.py --raw data/raw --out data/processed\n"
        "python src/forecast.py --processed data/processed/analysis_ready.parquet --out data/processed\n"
        "python src/risk.py --forecast data/processed/forecast.csv "
        "--processed data/processed/analysis_ready.parquet --out data/processed\n"
        "```"
    )
    st.stop()

analysis_df, forecast_df, risk_df, backtest = data

if risk_df.empty:
    st.info("Pipeline ran but produced no SKU risk rows — check the data-quality report.")
    st.stop()

# --- Sidebar filters -------------------------------------------------------
st.sidebar.header("Filters")
categories = sorted(risk_df["category"].dropna().unique().tolist())
selected_categories = st.sidebar.multiselect("Category", categories, default=categories)
quadrants = sorted(risk_df["quadrant"].unique().tolist())
selected_quadrants = st.sidebar.multiselect("Risk quadrant", quadrants, default=quadrants)
sku_search = st.sidebar.text_input("Search SKU ID")

filtered = risk_df[
    risk_df["category"].isin(selected_categories) & risk_df["quadrant"].isin(selected_quadrants)
]
if sku_search:
    filtered = filtered[filtered["sku_id"].str.contains(sku_search, case=False, na=False)]

# --- Headline metrics --------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("SKUs in view", len(filtered))
col2.metric("Sales at risk (₹)", f"{filtered['sales_at_risk_inr'].sum():,.0f}")
col3.metric("Capital locked (₹)", f"{filtered['capital_locked_inr'].sum():,.0f}")
if backtest:
    col4.metric(
        "Forecast WAPE (model vs baseline)",
        f"{backtest['wape_model']:.1%}",
        delta=f"{(backtest['wape_baseline'] - backtest['wape_model']):.1%} better than naive",
    )

st.divider()

# --- Decisioning grid --------------------------------------------------
st.subheader("Decisioning view — stockout vs overstock risk")
if filtered.empty:
    st.info("No SKUs match the current filters.")
else:
    fig = px.scatter(
        filtered,
        x="overstock_risk",
        y="stockout_risk",
        size=filtered["sales_at_risk_inr"] + filtered["capital_locked_inr"] + 1,
        color="quadrant",
        hover_data=["sku_id", "category", "recommended_action", "sales_at_risk_inr", "capital_locked_inr"],
        labels={"overstock_risk": "Overstock risk →", "stockout_risk": "Stockout risk →"},
        color_discrete_map={
            "Reorder now": "#d1495b",
            "Markdown / clear": "#6c5ce7",
            "Watch / volatile": "#e1a730",
            "Healthy": "#2a9d8f",
        },
    )
    fig.add_hline(y=0.5, line_dash="dot", line_color="gray")
    fig.add_vline(x=0.5, line_dash="dot", line_color="gray")
    fig.update_layout(height=450)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Prioritised action list --------------------------------------------------
st.subheader("Prioritised reorder / markdown list")
priority = filtered[filtered["quadrant"] != "Healthy"].copy()
priority["priority_value_inr"] = priority["sales_at_risk_inr"] + priority["capital_locked_inr"]
priority = priority.sort_values("priority_value_inr", ascending=False)

if priority.empty:
    st.success("No SKUs currently need action — all healthy within the current filters.")
else:
    st.dataframe(
        priority[[
            "sku_id", "category", "quadrant", "recommended_action",
            "stockout_risk", "overstock_risk",
            "sales_at_risk_inr", "capital_locked_inr",
            "on_hand_units", "on_order_units", "lead_time_days",
        ]],
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# --- Per-SKU forecast detail --------------------------------------------------
st.subheader("Forecast detail for a single SKU")
sku_options = sorted(filtered["sku_id"].unique().tolist()) if not filtered.empty else []
if sku_options:
    chosen_sku = st.selectbox("Choose a SKU", sku_options)
    hist = analysis_df[analysis_df["sku_id"] == chosen_sku].sort_values("date").tail(90)
    fut = forecast_df[forecast_df["sku_id"] == chosen_sku].sort_values("date")

    fig2 = px.line(hist, x="date", y="units_sold", labels={"units_sold": "Units sold"})
    fig2.add_scatter(x=fut["date"], y=fut["forecast"], mode="lines", name="Forecast")
    fig2.add_scatter(x=fut["date"], y=fut["baseline"], mode="lines", name="Seasonal-naive baseline",
                      line=dict(dash="dot"))
    fig2.add_scatter(
        x=list(fut["date"]) + list(fut["date"][::-1]),
        y=list(fut["upper_80"]) + list(fut["lower_80"][::-1]),
        fill="toself", fillcolor="rgba(108,92,231,0.15)", line=dict(color="rgba(0,0,0,0)"),
        name="80% interval", showlegend=True,
    )
    fig2.update_layout(height=400, legend=dict(orientation="h"))
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No SKUs to display for the current filters.")
