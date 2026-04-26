import numpy as np
import pandas as pd

from gold.io import KEY_COLS

PRECEDENCE = ("gmd", "wdi", "macro")

_INCOME_GROUP_MAP = {
    0.0: "Low income",
    1.0: "Lower middle income",
    2.0: "Upper middle income",
    3.0: "High income",
}

NO_INTERPOLATE = {
    "sov_debt_crisis", "currency_crisis", "banking_crisis", "income_group",
    "crisis_any", "flag_score", "SovDebtCrisis", "CurrencyCrisis",
    "BankingCrisis", "crisis_composite",
}


def _rank_source(source_series: pd.Series) -> pd.Series:
    rank_map = {s: i for i, s in enumerate(PRECEDENCE)}
    return source_series.str.lower().map(rank_map).fillna(999)


def apply_source_precedence(silver: pd.DataFrame, indicator: str) -> pd.DataFrame:
    df = silver[silver["indicator"] == indicator].copy()
    df["_rank"] = _rank_source(df["source"])
    df = df.sort_values("_rank").drop_duplicates(subset=["country_code", "year"], keep="first")
    return df.drop(columns="_rank")


def pivot_indicators(silver: pd.DataFrame, indicator_map: dict) -> pd.DataFrame:
    wide = None
    for ind, col in indicator_map.items():
        df = apply_source_precedence(silver, ind)[KEY_COLS + ["value"]].rename(
            columns={"value": col}
        )
        wide = df if wide is None else wide.merge(df, on=KEY_COLS, how="outer")
    return wide if wide is not None else pd.DataFrame(columns=KEY_COLS)


def get_group_join(silver: pd.DataFrame) -> pd.DataFrame:
    inc = (
        apply_source_precedence(silver, "income_group_encoded")[KEY_COLS + ["value"]]
        .rename(columns={"value": "income_group"})
        .assign(income_group=lambda df: df["income_group"].map(_INCOME_GROUP_MAP))
    )
    dev = (
        apply_source_precedence(silver, "development_group")[KEY_COLS + ["value"]]
        .rename(columns={"value": "development_group"})
    )
    return inc.merge(
        dev[["country_code", "year", "development_group"]],
        on=["country_code", "year"],
        how="outer",
    )


def interpolate_numeric(df: pd.DataFrame, skip_cols: list = None) -> pd.DataFrame:
    skip = set(KEY_COLS) | set(skip_cols or []) | NO_INTERPOLATE
    num_cols = [
        c for c in df.columns
        if c not in skip and pd.api.types.is_numeric_dtype(df[c])
    ]
    df = df.copy()
    for col in num_cols:
        df[col] = (
            df.groupby("country_code")[col]
            .transform(lambda s: s.interpolate(method="linear", limit=2, limit_direction="both"))
        )
    return df


def add_completeness(df: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [c for c in df.columns if c not in KEY_COLS]
    df = df.copy()
    df["completeness_score"] = df[feature_cols].notna().mean(axis=1).round(4)
    return df


def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    d = den.replace(0, np.nan)
    return num.where(d.notna()) / d
