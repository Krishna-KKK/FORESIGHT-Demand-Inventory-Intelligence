"""
Project FORESIGHT — D1 Data pipeline.

Ingests the four raw extracts, cleans and unifies them into one
analysis-ready dataset. Every cleaning decision is coded (not manual)
and logged so it can be audited, per Section 09 acceptance criteria.

Usage:
    python src/pipeline.py --raw data/raw --out data/processed
"""
import argparse
import json
import logging
import os

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("pipeline")

# Canonical category names — messy source labels get mapped onto these.
CATEGORY_MAP = {
    "furniture": "Furniture",
    "decor": "Decor",
    "décor": "Decor",
    "small appliances": "Small Appliances",
    "small appliance": "Small Appliances",
    "textiles": "Textiles",
    "textile": "Textiles",
}


def load_raw(raw_dir: str) -> dict:
    files = {
        "sales_daily": "sales_daily.csv",
        "sku_master": "sku_master.csv",
        "calendar": "calendar.csv",
        "inventory_snapshots": "inventory_snapshots.csv",
    }
    data = {}
    for key, fname in files.items():
        path = os.path.join(raw_dir, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Expected raw extract not found: {path}")
        date_cols = [c for c in ["date", "launch_date"] if c in pd.read_csv(path, nrows=0).columns]
        data[key] = pd.read_csv(path, parse_dates=date_cols)
    return data


def clean_sku_master(df: pd.DataFrame, log_report: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.drop_duplicates(subset="sku_id").copy()
    log_report["sku_master_duplicates_removed"] = n0 - len(df)

    df["category"] = (
        df["category"].str.strip().str.lower().map(CATEGORY_MAP).fillna(df["category"])
    )
    df["subcategory"] = df["subcategory"].str.strip()

    bad_price = (df["unit_cost"] <= 0) | (df["list_price"] <= 0)
    log_report["sku_master_bad_price_rows"] = int(bad_price.sum())
    df = df[~bad_price]
    return df


def clean_sales_daily(df: pd.DataFrame, sku_ids: set, log_report: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.drop_duplicates(subset=["date", "sku_id"]).copy()
    log_report["sales_duplicates_removed"] = n0 - len(df)

    df = df[df["sku_id"].isin(sku_ids)]

    missing_price = int(df["unit_price"].isna().sum())
    log_report["sales_missing_price_rows"] = missing_price
    # Impute missing price with that SKU's median price rather than dropping the row —
    # units_sold and revenue are still valid signal even without a clean price.
    df["unit_price"] = df.groupby("sku_id")["unit_price"].transform(lambda s: s.fillna(s.median()))

    df["units_sold"] = df["units_sold"].clip(lower=0)
    df["promo_flag"] = df["promo_flag"].fillna(0).astype(int)
    return df


def clean_inventory(df: pd.DataFrame, sku_ids: set, log_report: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.drop_duplicates(subset=["date", "sku_id"]).copy()
    log_report["inventory_duplicates_removed"] = n0 - len(df)
    df = df[df["sku_id"].isin(sku_ids)]
    for col in ["on_hand_units", "on_order_units"]:
        df[col] = df[col].clip(lower=0)
    return df


def build_analysis_dataset(sales: pd.DataFrame, sku_master: pd.DataFrame,
                            calendar: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    df = sales.merge(sku_master, on="sku_id", how="left", validate="many_to_one")
    df = df.merge(calendar, on="date", how="left", validate="many_to_one")

    # Inventory is a periodic (weekly) snapshot, not daily — forward-fill per SKU
    # onto the daily grain so every sales row has a known current stock position.
    frames = []
    for sku_id, g in inventory.sort_values("date").groupby("sku_id"):
        g = g.set_index("date").reindex(pd.date_range(g["date"].min(), g["date"].max(), freq="D"))
        g["sku_id"] = sku_id
        g = g.ffill().rename_axis("date").reset_index()
        frames.append(g)
    inv_daily = pd.concat(frames, ignore_index=True) if frames else inventory.copy()

    df = df.merge(inv_daily, on=["date", "sku_id"], how="left", suffixes=("", "_inv"))
    df = df.sort_values(["sku_id", "date"]).reset_index(drop=True)
    return df


def run(raw_dir: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    log_report = {}

    raw = load_raw(raw_dir)
    sku_master = clean_sku_master(raw["sku_master"], log_report)
    sku_ids = set(sku_master["sku_id"])
    sales = clean_sales_daily(raw["sales_daily"], sku_ids, log_report)
    inventory = clean_inventory(raw["inventory_snapshots"], sku_ids, log_report)
    calendar = raw["calendar"]

    analysis_df = build_analysis_dataset(sales, sku_master, calendar, inventory)

    out_path = os.path.join(out_dir, "analysis_ready.parquet")
    analysis_df.to_parquet(out_path, index=False)

    log_report["output_rows"] = len(analysis_df)
    log_report["output_skus"] = int(analysis_df["sku_id"].nunique())
    log_report["date_range"] = [str(analysis_df["date"].min()), str(analysis_df["date"].max())]

    report_path = os.path.join(out_dir, "data_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(log_report, f, indent=2)

    log.info("Wrote analysis-ready dataset: %s (%d rows)", out_path, len(analysis_df))
    log.info("Wrote data-quality report: %s", report_path)
    log.info(json.dumps(log_report, indent=2))
    return analysis_df, log_report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()
    run(args.raw, args.out)
