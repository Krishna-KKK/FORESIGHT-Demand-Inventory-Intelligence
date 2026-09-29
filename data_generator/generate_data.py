"""
Project FORESIGHT — synthetic data generator.

Generates the four raw extracts described in the brief (Section 05):
    sales_daily.csv, sku_master.csv, calendar.csv, inventory_snapshots.csv

The data is deliberately imperfect (missing values, a few duplicates,
inconsistent category labels) so that cleaning is a real part of the
pipeline, matching what a real client extract would look like.

Usage:
    python data_generator/generate_data.py --out data/raw --n-skus 200 --days 730 --seed 42
"""
import argparse
import os
import numpy as np
import pandas as pd

CATEGORIES = {
    "Furniture": ["Chairs", "Tables", "Shelving"],
    "Decor": ["Wall Art", "Rugs", "Lighting"],
    "Small Appliances": ["Kitchen", "Climate", "Cleaning"],
    "Textiles": ["Bedding", "Cushions", "Throws"],
}

# Inconsistent labels deliberately injected to mimic messy real-world extracts
CATEGORY_LABEL_VARIANTS = {
    "Furniture": ["Furniture", "furniture", "FURNITURE"],
    "Decor": ["Decor", "Décor", "decor"],
    "Small Appliances": ["Small Appliances", "Small Appliance", "small appliances"],
    "Textiles": ["Textiles", "textiles", "Textile"],
}


def make_calendar(start_date: str, days: int) -> pd.DataFrame:
    dates = pd.date_range(start=start_date, periods=days, freq="D")
    cal = pd.DataFrame({"date": dates})
    cal["week"] = cal["date"].dt.isocalendar().week.astype(int)
    cal["month"] = cal["date"].dt.month
    cal["season"] = cal["month"].map(
        lambda m: (
            "Winter" if m in (12, 1, 2) else
            "Spring" if m in (3, 4, 5) else
            "Summer" if m in (6, 7, 8) else
            "Autumn"
        )
    )
    # A handful of fixed holidays + a few random promo events
    cal["is_holiday"] = cal["date"].dt.strftime("%m-%d").isin(
        ["01-01", "01-26", "08-15", "10-02", "12-25"]
    ).astype(int)

    rng = np.random.default_rng(7)
    promo_dates = rng.choice(cal["date"], size=max(4, days // 90), replace=False)
    promo_names = ["Spring Sale", "Summer Clearance", "Festive Sale", "New Year Sale",
                   "Monsoon Offer", "End of Season Sale"]
    cal["promo_event"] = None
    for i, d in enumerate(promo_dates):
        window = cal["date"].between(d, d + pd.Timedelta(days=6))
        cal.loc[window, "promo_event"] = promo_names[i % len(promo_names)]
    return cal


def make_sku_master(n_skus: int, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    cats = list(CATEGORIES.keys())
    for i in range(n_skus):
        cat = cats[i % len(cats)]
        subcat = rng.choice(CATEGORIES[cat])
        label_variant = rng.choice(CATEGORY_LABEL_VARIANTS[cat])  # messy label on purpose
        unit_cost = round(rng.uniform(150, 4000), 2)
        margin = rng.uniform(1.4, 2.6)
        list_price = round(unit_cost * margin, 2)
        launch_offset = rng.integers(0, 500)
        rows.append({
            "sku_id": f"NB-{1000 + i}",
            "category": label_variant,
            "subcategory": subcat,
            "launch_date": pd.Timestamp("2024-01-01") - pd.Timedelta(days=int(launch_offset)),
            "unit_cost": unit_cost,
            "list_price": list_price,
        })
    df = pd.DataFrame(rows)
    # inject a couple of duplicate rows, matching "expect the odd duplicate" in the brief
    dupes = df.sample(n=min(2, len(df)), random_state=1)
    return pd.concat([df, dupes], ignore_index=True)


def make_sales_and_inventory(sku_master: pd.DataFrame, calendar: pd.DataFrame,
                              rng: np.random.Generator):
    sales_rows = []
    inv_rows = []
    dates = calendar["date"].tolist()
    promo_dates = set(calendar.loc[calendar["promo_event"].notna(), "date"])
    holiday_dates = set(calendar.loc[calendar["is_holiday"] == 1, "date"])

    for _, sku in sku_master.drop_duplicates(subset="sku_id").iterrows():
        base_demand = rng.uniform(2, 40)          # units/day baseline
        trend = rng.uniform(-0.0005, 0.0015)      # slow drift over time
        season_amp = rng.uniform(0.1, 0.5)
        season_phase = rng.uniform(0, 2 * np.pi)
        noise_scale = rng.uniform(0.15, 0.4)
        launch = sku["launch_date"]

        on_hand = rng.uniform(80, 400)
        lead_time = int(rng.integers(5, 21))
        reorder_point = round(base_demand * lead_time * 1.3, 1)

        for t, d in enumerate(dates):
            if d < launch:
                continue  # SKU not yet sold
            seasonal = 1 + season_amp * np.sin(2 * np.pi * t / 365 + season_phase)
            promo_lift = 1.6 if d in promo_dates else 1.0
            holiday_lift = 1.3 if d in holiday_dates else 1.0
            mean_demand = max(
                0.0,
                base_demand * (1 + trend * t) * seasonal * promo_lift * holiday_lift,
            )
            units_sold = rng.poisson(lam=max(mean_demand, 0.01))
            units_sold = max(0, int(units_sold * (1 + rng.normal(0, noise_scale))))

            price = sku["list_price"]
            if d in promo_dates and rng.random() < 0.8:
                price = round(price * rng.uniform(0.7, 0.9), 2)

            sales_rows.append({
                "date": d,
                "sku_id": sku["sku_id"],
                "units_sold": units_sold,
                "revenue": round(units_sold * price, 2),
                "unit_price": price,
                "promo_flag": int(d in promo_dates),
            })

            # inventory draws down with sales, replenishes stochastically near reorder point
            on_hand = max(0, on_hand - units_sold)
            on_order = 0
            if on_hand <= reorder_point and rng.random() < 0.3:
                on_order = round(base_demand * lead_time * rng.uniform(1.2, 2.0), 0)
                on_hand += on_order * (rng.random() < 0.2)  # occasional same-day partial receipt

            if t % 7 == 0:  # snapshot weekly, matching "periodic stock position" in the brief
                inv_rows.append({
                    "date": d,
                    "sku_id": sku["sku_id"],
                    "on_hand_units": round(on_hand, 0),
                    "on_order_units": on_order,
                    "lead_time_days": lead_time,
                    "reorder_point": reorder_point,
                })

    sales = pd.DataFrame(sales_rows)
    inventory = pd.DataFrame(inv_rows)

    # Inject realistic messiness: missing values + a few duplicate rows
    miss_idx = sales.sample(frac=0.01, random_state=2).index
    sales.loc[miss_idx, "unit_price"] = np.nan
    dupe_rows = sales.sample(n=min(20, len(sales)), random_state=3)
    sales = pd.concat([sales, dupe_rows], ignore_index=True)

    return sales, inventory


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--n-skus", type=int, default=200)
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--start-date", default="2024-01-01")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out, exist_ok=True)

    calendar = make_calendar(args.start_date, args.days)
    sku_master = make_sku_master(args.n_skus, rng)
    sales, inventory = make_sales_and_inventory(sku_master, calendar, rng)

    calendar.to_csv(os.path.join(args.out, "calendar.csv"), index=False)
    sku_master.to_csv(os.path.join(args.out, "sku_master.csv"), index=False)
    sales.to_csv(os.path.join(args.out, "sales_daily.csv"), index=False)
    inventory.to_csv(os.path.join(args.out, "inventory_snapshots.csv"), index=False)

    print(f"Wrote {len(sales)} sales rows, {len(inventory)} inventory snapshots, "
          f"{len(sku_master)} SKU rows, {len(calendar)} calendar rows to {args.out}/")


if __name__ == "__main__":
    main()
