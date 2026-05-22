from __future__ import annotations

from pathlib import Path

import pandas as pd

from warehouse.bigquery_warehouse_validation import (
    SILVER_NON_NULL_CONTRACT_COLUMNS,
    compute_null_counts,
    get_table_contract_columns,
    load_table_contract,
    summarize_dataframe_validation,
    validate_completeness_score,
    validate_country_code_iso3,
    validate_crisis_columns,
    validate_year_range,
)


def test_validation_helpers() -> None:
    df = pd.DataFrame(
        [
            {
                "country_code": "VNM",
                "country": "Viet Nam",
                "year": 2020,
                "run_id": "r1",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00",
                "completeness_score": 0.5,
                "SovDebtCrisis": 1,
                "crisis_composite": 2,
            }
        ]
    )
    summary = summarize_dataframe_validation(
        df=df,
        table_name="dummy",
        required_columns=["country_code", "country", "year", "run_id", "run_date", "loaded_at"],
    )
    assert summary.passed is True
    assert validate_country_code_iso3(df) == 0
    assert validate_year_range(df) == 0
    assert validate_completeness_score(df) == 0
    assert validate_crisis_columns(df)["SovDebtCrisis"] == 0


def test_null_counts_for_non_null_contract_columns() -> None:
    df = pd.DataFrame(
        [
            {
                "country_code": "VNM",
                "country": "Viet Nam",
                "year": 2020,
                "indicator": "x",
                "source": "wdi",
                "run_id": "r1",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00",
            },
            {
                "country_code": None,
                "country": "Viet Nam",
                "year": 2021,
                "indicator": "x",
                "source": "wdi",
                "run_id": "r1",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00",
            },
        ]
    )
    counts = compute_null_counts(df, SILVER_NON_NULL_CONTRACT_COLUMNS)
    assert counts["country_code"] == 1


def test_table_contract_columns_exist_for_gold() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    contract = load_table_contract(repo_root / "contracts" / "table_contract.yaml")
    columns = get_table_contract_columns(contract, "gold", "gold_growth_dynamics")
    assert "country_code" in columns
    assert "run_id" in columns

