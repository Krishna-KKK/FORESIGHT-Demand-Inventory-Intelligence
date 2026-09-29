# FORESIGHT — Executive Readout

**To:** Head of Operations, Finance Lead — NorthBay Living
**From:** Data Science & Analytics engagement team
**Re:** 4-week Demand & Inventory Intelligence engagement — findings and recommendation

*Figures below come from an actual run of this repository's pipeline
(`run_pipeline.sh`) on the bundled synthetic dataset — not illustrative
placeholders. Re-run the pipeline on your real extract to refresh them.*

## Headline

Running the pipeline against two years of data across 200 SKUs: **63 SKUs
(31.5%) are flagged for reorder attention** and **61 SKUs (30.5%) are
flagged for markdown/clearance** right now. Together that represents
**≈₹4.63 crore in sales at risk** from potential stockouts and **≈₹6.19
crore in capital locked** in slow-moving stock. The forecasting model
beats a seasonal-naive baseline by **26% on WAPE** (28.7% vs. 38.8%) on
honest, rolling-origin backtesting — it is worth trusting over gut-feel.

## What we built

1. **A weekly, SKU-level demand forecast**, backtested on 4 rolling folds
   of held-out history, never trained on data from the future relative to
   what it's predicting.
2. **A stockout/overstock risk score for every SKU**, combining the
   forecast with current inventory position (on-hand, on-order, lead
   time, reorder point), with a plain-language recommended action and a
   rupee value attached to each.
3. **A planning dashboard** the team can filter by category, drill into
   any SKU's forecast, and use to work a prioritised reorder/markdown
   list — without needing a data scientist in the room.
4. **A scoring API** returning forecast + risk for any SKU or batch, so
   this can plug into other tools later.

## Accuracy — stated honestly

| Metric | Seasonal-naive baseline | FORESIGHT model |
|---|---|---|
| WAPE (lower is better) | 38.8% | **28.7%** |

The model wins clearly on backtest, so it is what's shipped. Had it not
won, the pipeline is built to ship the honest baseline instead and say so
— that's a design decision (see `src/forecast.py`), not an incidental
result. WAPE in the high 20s–high 30s reflects the genuinely noisy,
low-volume nature of SKU-day demand in this dataset; it should fall
further with more history per SKU or coarser (weekly, not daily) targets.

**Where to be cautious:** newly launched SKUs have too little history for
the model's longer lag features and lean more on short-window and
category-level signal — treat forecasts for SKUs launched in the last
~8 weeks as lower-confidence.

## What this is worth in rupees

- **Sales at risk (stockout exposure):** ≈₹4.63 crore across flagged SKUs
- **Capital locked (overstock exposure):** ≈₹6.19 crore across flagged SKUs

These are not abstract risk scores — they are forecast demand times list
price (for stockout exposure) and excess on-hand stock times unit cost
(for capital locked), computed per SKU in `src/risk.py` and fully
auditable in `data/processed/risk_scores.csv`.

## Recommendation

1. **This week:** action the "Reorder now" list first — it is sorted by
   rupee exposure, so the top rows are where a missed reorder costs the
   most.
2. **This month:** work through the "Markdown / clear" list to free
   locked capital, prioritising by `capital_locked_inr`.
3. **Ongoing:** re-run the pipeline weekly (it is fully reproducible —
   `bash run_pipeline.sh`) so the dashboard and API always reflect current
   stock and the latest forecast.

## Limitations, in plain language

- This is trained and validated on the extracts provided, not a live
  feed — it needs to be re-run regularly to stay current (no live system
  integration, by design — see the engagement's scope boundary).
- Forecast intervals are an approximation from recent volatility, not a
  fully calibrated statistical interval — good for a sense of confidence,
  not a guarantee.
- Risk thresholds (0.5 / 0.5) are simple and explainable by design; they
  are a reasonable starting point, not yet tuned against a specific
  target service level.
