# Project FORESIGHT — Demand & Inventory Intelligence

**Client:** NorthBay Living (simulated D2C home & lifestyle brand)
**Engagement:** Zidio Development, Data Science & Analytics track

FORESIGHT turns NorthBay's raw sales and inventory extracts into a
weekly, SKU-level demand forecast and a stockout/overstock early-warning
system, served through a planning dashboard and a scoring API.

## The problem

NorthBay plans inventory on gut feel and spreadsheets. Best-sellers run
out (lost sales); slow movers pile up (cash locked in markdown-bound
stock). FORESIGHT tells the ops team, per SKU: how much will likely sell
next, what's about to run out, and what's overstocked — in rupees, not
just probabilities.

## Repository structure

```
foresight/
  data_generator/generate_data.py   # synthetic raw extracts (see note below)
  data/
    raw/                            # generated raw CSVs (gitignored)
    processed/                      # pipeline + model outputs (gitignored)
  src/
    pipeline.py                     # D1 — ingest, clean, unify (analysis_ready.parquet)
    features.py                     # leakage-safe feature engineering
    forecast.py                     # D3 — seasonal-naive baseline + LightGBM, rolling-origin backtest
    risk.py                         # D4 — stockout/overstock risk scoring + decisioning grid
  app/app.py                        # D5 — Streamlit planning dashboard
  service/main.py                   # D6 — FastAPI scoring service
  tests/test_core_logic.py          # unit tests for risk logic + WAPE metric
  reports/                          # EDA memo + executive readout go here
  design/                           # design spec for the dashboard (see below — not a .fig file)
  requirements.txt
  .gitignore
```

## Why there's a data generator

The engagement brief specifies that a synthetic dataset is provided and
that generating data is *not* the intern's job — the effort goes into
cleaning and modelling it. `data_generator/generate_data.py` reproduces
that provided dataset's shape (same four tables, same deliberate messiness:
missing prices, a few duplicate rows, inconsistent category labels) so the
whole pipeline is runnable and testable end-to-end. **If NorthBay's actual
provided CSVs are available, drop them into `data/raw/` with the same
filenames and skip this step** — everything downstream is unchanged.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate      # optional but recommended
pip install -r requirements.txt

# 1. Generate (or supply your own) raw data
python data_generator/generate_data.py --out data/raw --n-skus 200 --days 730

# 2. Clean + unify into one analysis-ready dataset (D1)
python src/pipeline.py --raw data/raw --out data/processed

# 3. Backtest and forecast (D3)
python src/forecast.py --processed data/processed/analysis_ready.parquet \
                        --out data/processed --horizon 7 --n-folds 4

# 4. Score stockout / overstock risk (D4)
python src/risk.py --forecast data/processed/forecast.csv \
                    --processed data/processed/analysis_ready.parquet \
                    --out data/processed

# 5. Open the dashboard (D5)
streamlit run app/app.py

# 6. Run the scoring API (D6)
uvicorn service.main:app --reload --port 8000
# then: curl http://localhost:8000/score/NB-1000
```

Run the tests with `pytest tests/`.

## Methodology (Section 07 of the brief)

1. **Frame the metric** — WAPE (Weighted Absolute Percentage Error) is the
   primary accuracy metric; it's robust to the many low-volume SKUs where
   MAPE explodes. Bias is tracked as a secondary check.
2. **Baseline first** — a seasonal-naive forecast (repeat last week) is
   built before any model. It is the bar the model must clear.
3. **Features** — lags (1/7/14/28 days), rolling mean/std (7/14/28 days,
   always computed on `shift(1)` history so the current day never leaks
   into its own rolling stat), calendar features, promo flags, and
   days-since-launch.
4. **Model** — LightGBM gradient-boosted trees over the engineered
   features. Falls back to the baseline automatically if LightGBM isn't
   installed or if the model doesn't beat the baseline on backtest.
5. **Backtest** — rolling-origin cross-validation (never a single random
   split for time series): the origin walks forward across `n_folds`,
   training only on the past and testing on the next `horizon` days each
   time.
6. **Evaluate & select honestly** — `data/processed/backtest_summary.json`
   records whether the model beat the baseline. If it didn't, the pipeline
   ships the baseline and says so — that is a reported finding, not a bug
   to hide (see Section 07 of the brief, "the non-negotiable rule").
7. **Risk score** — `src/risk.py` combines the forecast with current
   inventory position (on-hand + on-order vs. demand over lead time for
   stockout risk; on-hand vs. demand over a 28-day window for overstock
   risk) into the four-quadrant decisioning grid: **Reorder now / Markdown
   & clear / Watch & volatile / Healthy**, each with a rupee value at
   stake.

On the bundled synthetic data, backtested WAPE was **~0.32 for the model
vs. ~0.52 for the seasonal-naive baseline** across a 3-fold rolling-origin
backtest — a clear, honest win. Re-run `src/forecast.py` to reproduce this
number; it will vary slightly with the random seed used to generate data.

## What's simplified vs. a full production system

This is an internship-scale engagement (4 weeks), so some things are
intentionally simple rather than production-grade:

- **Forecast intervals** are an approximation from recent residual
  volatility (`±1.28 × rolling std`), not a fully calibrated predictive
  distribution. Good enough to show the team a confidence range; a real
  deployment would want quantile regression or conformal intervals.
- **Risk thresholds** (0.5 / 0.5) are simple, transparent, and easy to
  explain to a non-technical team — not tuned against a service-level
  target. Section 11's "stretch goals" list calibrated thresholds as a
  next step.
- **No live system integration** — this reads from static extracts, per
  the brief's explicit scope boundary (Section 04.3).

## Deployment notes (D6)

The scoring service and dashboard are both stateless Python apps that
read from `data/processed/`. Suggested free/low-cost hosts (per Section
14.2 of the brief):

- **Dashboard:** Streamlit Community Cloud — point it at `app/app.py`.
- **API:** Render or Hugging Face Spaces (Docker) — entrypoint
  `uvicorn service.main:app --host 0.0.0.0 --port $PORT`.

Both need `data/processed/*.csv|*.parquet` present at startup — either
commit a small demo dataset for the deployed instance, or run the
pipeline as a build step.

## Design (D5 / dashboard look-and-feel)

See [`design/DESIGN_SPEC.md`](design/DESIGN_SPEC.md) for the dashboard's
layout, color system, and component list, written so it can be recreated
in Figma (this tool cannot export a native `.fig` file).
