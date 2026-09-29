"""
Project FORESIGHT — D6 Deployed scoring service.

Run locally with:
    uvicorn service.main:app --reload --port 8000

Then, e.g.:
    curl http://localhost:8000/score/NB-1000
    curl -X POST http://localhost:8000/score/batch -H "Content-Type: application/json" \
         -d '{"sku_ids": ["NB-1000", "NB-1001"]}'

Reads the same data/processed/ outputs the dashboard uses. Deploy target
suggestions (Streamlit Community Cloud / Hugging Face Spaces / Render) are
in the README.
"""
import os
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

app = FastAPI(
    title="Project FORESIGHT — Scoring Service",
    description="Returns demand forecast and stockout/overstock risk for NorthBay Living SKUs.",
    version="1.0.0",
)


class BatchRequest(BaseModel):
    sku_ids: List[str]


class ForecastPoint(BaseModel):
    date: str
    forecast: float
    baseline: float
    lower_80: float
    upper_80: float


class SkuScore(BaseModel):
    sku_id: str
    found: bool
    category: Optional[str] = None
    stockout_risk: Optional[float] = None
    overstock_risk: Optional[float] = None
    quadrant: Optional[str] = None
    recommended_action: Optional[str] = None
    sales_at_risk_inr: Optional[float] = None
    capital_locked_inr: Optional[float] = None
    forecast: Optional[List[ForecastPoint]] = None


def _load_risk() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "risk_scores.csv")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=503,
            detail="Risk scores not found. Run the pipeline (see README) before calling this service.",
        )
    return pd.read_csv(path)


def _load_forecast() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "forecast.csv")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=503,
            detail="Forecast not found. Run the pipeline (see README) before calling this service.",
        )
    return pd.read_csv(path, parse_dates=["date"])


def _score_one(sku_id: str, risk_df: pd.DataFrame, forecast_df: pd.DataFrame) -> SkuScore:
    row = risk_df[risk_df["sku_id"] == sku_id]
    if row.empty:
        return SkuScore(sku_id=sku_id, found=False)
    row = row.iloc[0]
    fut = forecast_df[forecast_df["sku_id"] == sku_id].sort_values("date")
    forecast_points = [
        ForecastPoint(
            date=str(r["date"].date()),
            forecast=float(r["forecast"]),
            baseline=float(r["baseline"]),
            lower_80=float(r["lower_80"]),
            upper_80=float(r["upper_80"]),
        )
        for _, r in fut.iterrows()
    ]
    return SkuScore(
        sku_id=sku_id,
        found=True,
        category=row.get("category"),
        stockout_risk=float(row["stockout_risk"]),
        overstock_risk=float(row["overstock_risk"]),
        quadrant=row["quadrant"],
        recommended_action=row["recommended_action"],
        sales_at_risk_inr=float(row["sales_at_risk_inr"]),
        capital_locked_inr=float(row["capital_locked_inr"]),
        forecast=forecast_points,
    )


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "Project FORESIGHT scoring service",
        "endpoints": ["/score/{sku_id}", "/score/batch (POST)", "/health"],
    }


@app.get("/health", tags=["meta"])
def health():
    ok = os.path.exists(os.path.join(DATA_DIR, "risk_scores.csv"))
    return {"status": "ok" if ok else "pipeline_not_run"}


@app.get("/score/{sku_id}", response_model=SkuScore, tags=["scoring"])
def score_sku(sku_id: str):
    risk_df = _load_risk()
    forecast_df = _load_forecast()
    return _score_one(sku_id, risk_df, forecast_df)


@app.post("/score/batch", response_model=List[SkuScore], tags=["scoring"])
def score_batch(payload: BatchRequest):
    if not payload.sku_ids:
        raise HTTPException(status_code=400, detail="sku_ids must be a non-empty list.")
    risk_df = _load_risk()
    forecast_df = _load_forecast()
    return [_score_one(s, risk_df, forecast_df) for s in payload.sku_ids]
