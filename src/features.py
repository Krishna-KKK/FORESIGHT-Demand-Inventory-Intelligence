"""
Project FORESIGHT — feature engineering.

All features are computed using only information available up to and
including the row's own date (no future leakage). Lags and rolling
windows are shifted by at least 1 day before aggregation.
"""
import numpy as np
import pandas as pd


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["dow"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["dow"].isin([5, 6]).astype(int)
    df["month"] = df["date"].dt.month
    df["is_holiday"] = df["is_holiday"].fillna(0).astype(int)
    df["is_promo"] = df["promo_flag"].fillna(0).astype(int)
    df["has_promo_event"] = df["promo_event"].notna().astype(int)
    return df


def add_lag_rolling_features(df: pd.DataFrame, target_col: str = "units_sold") -> pd.DataFrame:
    df = df.sort_values(["sku_id", "date"]).copy()
    g = df.groupby("sku_id")[target_col]

    for lag in [1, 7, 14, 28]:
        df[f"lag_{lag}"] = g.shift(lag)

    for window in [7, 14, 28]:
        # shift(1) first so the current day's own value never leaks into its own rolling stat
        shifted = g.shift(1)
        df[f"roll_mean_{window}"] = shifted.groupby(df["sku_id"]).transform(
            lambda s: s.rolling(window, min_periods=max(2, window // 3)).mean()
        )
        df[f"roll_std_{window}"] = shifted.groupby(df["sku_id"]).transform(
            lambda s: s.rolling(window, min_periods=max(2, window // 3)).std()
        )

    df["days_since_launch"] = (df["date"] - df["launch_date"]).dt.days.clip(lower=0)
    return df


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = add_calendar_features(df)
    df = add_lag_rolling_features(df)
    return df


FEATURE_COLUMNS = [
    "dow", "is_weekend", "month", "is_holiday", "is_promo", "has_promo_event",
    "lag_1", "lag_7", "lag_14", "lag_28",
    "roll_mean_7", "roll_mean_14", "roll_mean_28",
    "roll_std_7", "roll_std_14", "roll_std_28",
    "days_since_launch", "unit_price",
]
CATEGORICAL_COLUMNS = ["category", "subcategory"]
