from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


SILVER_REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "indicator",
    "value",
    "source",
    "run_id",
    "run_date",
    "loaded_at",
)

SILVER_NON_NULL_CONTRACT_COLUMNS = (
    "country_code",
    "country",
    "year",
    "indicator",
    "source",
    "run_id",
    "run_date",
    "loaded_at",
)

ALLOWED_SOURCES = ("wdi", "gmd", "macro")


@dataclass(frozen=True)
class DataFrameValidationSummary:
    table_name: str
    row_count: int
    column_count: int
    duplicate_key_count: int
    null_counts: dict[str, int]
    missing_columns: list[str]

    @property
    def passed(self) -> bool:
        return self.row_count > 0 and self.duplicate_key_count == 0 and not self.missing_columns


def parse_table_id(table_id: str) -> tuple[str, str, str]:
    clean = str(table_id or "").strip()
    parts = clean.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"Invalid BigQuery table id: {table_id!r}")
    return parts[0], parts[1], parts[2]


def load_table_contract(contract_path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(contract_path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("table_contract.yaml must parse to a mapping.")
    return payload


def get_table_contract_columns(contract: dict[str, Any], section: str, table_name: str) -> list[str]:
    section_payload = contract.get(section) or {}
    table_payload = section_payload.get(table_name) or {}
    columns = table_payload.get("columns") or {}
    if isinstance(columns, dict):
        return list(columns.keys())
    required_columns = table_payload.get("required_columns") or []
    if isinstance(required_columns, list):
        return [str(item) for item in required_columns]
    return []


def validate_required_columns(df: pd.DataFrame, required_columns: list[str] | tuple[str, ...]) -> list[str]:
    return [column for column in required_columns if column not in df.columns]


def compute_null_counts(df: pd.DataFrame, columns: list[str] | tuple[str, ...]) -> dict[str, int]:
    return {column: int(df[column].isna().sum()) if column in df.columns else -1 for column in columns}


def validate_country_code_iso3(df: pd.DataFrame, column: str = "country_code") -> int:
    if column not in df.columns:
        return -1
    series = df[column]
    return int((~series.astype(str).str.fullmatch(r"[A-Z]{3}") | series.isna()).sum())


def validate_year_range(df: pd.DataFrame, column: str = "year", min_year: int = 1980, max_year: int = 2030) -> int:
    if column not in df.columns:
        return -1
    numeric = pd.to_numeric(df[column], errors="coerce")
    return int((numeric.isna() | ~numeric.between(min_year, max_year)).sum())


def validate_completeness_score(df: pd.DataFrame) -> int:
    if "completeness_score" not in df.columns:
        return 0
    series = pd.to_numeric(df["completeness_score"], errors="coerce")
    return int((series.notna() & ~series.between(0.0, 1.0)).sum())


def validate_crisis_columns(df: pd.DataFrame) -> dict[str, int]:
    checks: dict[str, int] = {}
    for column in ("SovDebtCrisis", "CurrencyCrisis", "BankingCrisis", "crisis_any"):
        if column in df.columns:
            checks[column] = int((df[column].notna() & ~df[column].isin([0, 1])).sum())
    if "crisis_composite" in df.columns:
        checks["crisis_composite"] = int(
            (df["crisis_composite"].notna() & ~df["crisis_composite"].isin([0, 1, 2, 3])).sum()
        )
    return checks


def validate_no_duplicate_keys(df: pd.DataFrame, key_columns: list[str] | tuple[str, ...]) -> int:
    missing = [column for column in key_columns if column not in df.columns]
    if missing:
        return -1
    return int(df.duplicated(subset=list(key_columns)).sum())


def summarize_dataframe_validation(
    *,
    df: pd.DataFrame,
    table_name: str,
    required_columns: list[str] | tuple[str, ...],
    key_columns: list[str] | tuple[str, ...] = ("country_code", "year"),
) -> DataFrameValidationSummary:
    missing_columns = validate_required_columns(df, required_columns)
    duplicate_key_count = validate_no_duplicate_keys(df, key_columns)
    null_counts = compute_null_counts(df, required_columns)
    return DataFrameValidationSummary(
        table_name=table_name,
        row_count=int(len(df)),
        column_count=int(len(df.columns)),
        duplicate_key_count=duplicate_key_count,
        null_counts=null_counts,
        missing_columns=missing_columns,
    )

