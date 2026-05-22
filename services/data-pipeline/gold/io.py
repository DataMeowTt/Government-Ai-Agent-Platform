import glob
import os

import pandas as pd

_SILVER_DIR = os.path.join("data", "processed_data", "processed.csv")

KEY_COLS = ["country_code", "country", "year"]


def load_silver(path: str = None) -> pd.DataFrame:
    directory = path or _SILVER_DIR
    parts = sorted(glob.glob(os.path.join(directory, "part-*.csv")))
    if not parts:
        raise FileNotFoundError(f"No Spark partition files found in: {directory}")
    return pd.read_csv(parts[0])


def validate(df: pd.DataFrame, table: str, crisis_check: bool = False) -> None:
    n           = len(df)
    n_countries = df["country_code"].nunique()
    yr_min      = int(df["year"].min())
    yr_max      = int(df["year"].max())
    null_rate   = df.isnull().mean().mean() * 100
    cs          = df["completeness_score"]

    print(f"\n[TABLE] {table}")
    print(f"  Rows          : {n}")
    print(f"  Countries     : {n_countries}")
    print(f"  Year range    : {yr_min} – {yr_max}")
    print(f"  Null rate     : {null_rate:.2f}%")
    print(f"  completeness  : mean={cs.mean():.4f}, min={cs.min():.4f}")

    assert df["country_code"].dropna().str.match(r"^[A-Z]{3}$").all(), \
        "country_code format error"
    assert df["year"].notna().all(), "year has nulls"
    assert df["completeness_score"].between(0.0, 1.0).all(), \
        "completeness_score out of [0,1]"
    if crisis_check and "crisis_composite" in df.columns:
        assert df["crisis_composite"].dropna().isin([0, 1, 2, 3]).all(), \
            "crisis_composite out of {0,1,2,3}"