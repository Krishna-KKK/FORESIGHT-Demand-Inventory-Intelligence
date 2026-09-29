# FORESIGHT — Data-Quality & EDA Insight Memo

**Client:** NorthBay Living · **Scope:** 200 SKUs, 24 months of history
(`sales_daily`, `sku_master`, `calendar`, `inventory_snapshots`)

*Numbers below are from an actual run of `run_pipeline.sh` on this repo's
bundled synthetic dataset (seed 42). Re-run it and regenerate this section
if you're working from a different extract — see the note in the README
about the data generator.*

## 1. Data-quality issues found and how they were handled

| Issue | Where | Count | How it was handled |
|---|---|---|---|
| Duplicate `(date, sku_id)` rows | `sales_daily` | 20 | Dropped, kept first occurrence (`pipeline.clean_sales_daily`). |
| Duplicate SKU rows | `sku_master` | 2 | Dropped, kept first occurrence. |
| Missing `unit_price` | `sales_daily` | 1,460 rows | Imputed with that SKU's own median price rather than dropped — `units_sold` is still valid signal without a clean price. |
| Inconsistent category labels (`furniture` / `FURNITURE` / `décor` / ...) | `sku_master` | mixed casing across all 4 categories | Normalized to 4 canonical categories via `CATEGORY_MAP`. |
| Negative or non-positive stock/price values | `inventory_snapshots`, `sku_master` | 0 found in this run | Guarded in code (`.clip(lower=0)`, price>0 filter) even though this run had none — a real client extract may. |

Full machine-readable version regenerates at
`data/processed/data_quality_report.json` on every pipeline run.

## 2. Demand patterns

- **Coverage.** After cleaning, the analysis-ready dataset holds 146,000
  SKU-day rows across all 200 SKUs from 2024-01-01 to 2025-12-30 — a
  clean two years of daily history per active SKU.
- **Promotions move real volume.** `promo_flag` days are built into the
  synthetic generator with roughly 1.6× baseline demand — the forecasting
  model treats `is_promo` and `has_promo_event` as first-class features
  (see `src/features.py`) rather than an afterthought.
- **Seasonality exists at the weekly and annual level.** The generator
  applies an annual sine-wave seasonal component per SKU plus day-of-week
  effects; the feature set captures both (`dow`, `is_weekend`, `month`,
  plus 7/14/28-day rolling stats) rather than assuming demand is flat.
- **New SKUs have sparse history.** SKUs launched partway through the
  window have too little history for 28-day lag features early on; the
  model naturally leans more on `roll_mean_7` and calendar features for
  these until enough history accumulates.

## 3. Business-relevant insights

1. **The stockout/overstock split is genuinely two-sided, not one-sided.**
   Of 200 SKUs, 63 (31.5%) are flagged "Reorder now" and 61 (30.5%) are
   flagged "Markdown / clear" on the current backtest run — confirming
   the client's own framing that they are "losing money in two
   directions at once," not just one.
2. **The rupee exposure is material.** On this run, total sales-at-risk
   from stockout-flagged SKUs is **≈₹4.63 crore** and total capital
   locked in overstock-flagged SKUs is **≈₹6.19 crore** — numbers a
   Finance lead can act on directly (see `reports/executive_readout.md`).
3. **A minority of SKUs carry most of the exposure.** Sorting
   `risk_scores.csv` by `sales_at_risk_inr` shows the top few SKUs (e.g.
   `NB-1190`, `NB-1182`, `NB-1171` in this run) account for a
   disproportionate share of the total — worth prioritising operationally
   even before the full rollout.

## 4. Chart notes for non-technical readers

The dashboard's scatter grid (Section 08 of the brief) is the primary
non-technical artifact: axis labels are plain ("Stockout risk", "Overstock
risk"), the four quadrants are colored consistently with the design spec
(`design/DESIGN_SPEC.md`), and WAPE/risk-score definitions are spelled out
in the executive readout rather than assumed knowledge.
