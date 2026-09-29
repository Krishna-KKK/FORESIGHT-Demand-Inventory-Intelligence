#!/usr/bin/env bash
# Project FORESIGHT — reproducible end-to-end run.
# From the repo root: bash run_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/4  Generating synthetic client extracts =="
python data_generator/generate_data.py --out data/raw --n-skus 200 --days 730 --seed 42

echo "== 2/4  Ingest, validate, clean (D1) =="
python src/pipeline.py --raw data/raw --out data/processed

echo "== 3/4  Backtest + forecast (D3) =="
cd src
python forecast.py --processed ../data/processed/analysis_ready.parquet \
                    --out ../data/processed --horizon 7 --n-folds 4
cd ..

echo "== 4/4  Stockout / overstock risk scoring (D4) =="
cd src
python risk.py --forecast ../data/processed/forecast.csv \
                --processed ../data/processed/analysis_ready.parquet \
                --out ../data/processed
cd ..

echo
echo "Pipeline complete. Next:"
echo "  streamlit run app/app.py"
echo "  uvicorn service.main:app --reload --port 8000"
