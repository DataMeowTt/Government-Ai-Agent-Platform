from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ops.pipeline_run_metadata import utc_now_iso
from warehouse.bigquery_warehouse_validation import (
    SILVER_NON_NULL_CONTRACT_COLUMNS,
    SILVER_REQUIRED_COLUMNS,
    compute_null_counts,
    get_table_contract_columns,
    load_table_contract,
    validate_completeness_score,
    validate_country_code_iso3,
    validate_crisis_columns,
    validate_no_duplicate_keys,
    validate_required_columns,
    validate_year_range,
)


SILVER_KEY_COLUMNS = ("country_code", "year", "indicator", "source")
WAREHOUSE_KEY_COLUMNS = ("country_code", "year")
METADATA_NON_NULL_COLUMNS = ("country_code", "country", "year", "run_id", "run_date", "loaded_at")
FALLBACK_REQUIRED_COLUMNS = {
    "analytics_clusters": [
        "country_code",
        "country",
        "year",
        "cluster_id",
        "latest_valid_year",
        "run_id",
        "run_date",
        "loaded_at",
    ]
}


def _default_contract_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [current.parent, *current.parents]
    for candidate in candidates:
        contract_path = candidate / "contracts" / "table_contract.yaml"
        if contract_path.exists():
            return contract_path
    raise FileNotFoundError(
        "Unable to resolve contracts/table_contract.yaml from "
        f"{current}"
    )


def _load_candidate_frame(payload: Any) -> pd.DataFrame:
    if isinstance(payload, pd.DataFrame):
        return payload.copy()

    path = Path(payload).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Candidate artifact not found: {path}")

    if path.is_file():
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path, encoding="utf-8")
        raise ValueError(f"Unsupported candidate artifact file type: {path.suffix}")

    parquet_files = sorted(path.rglob("*.parquet"))
    if parquet_files:
        return pd.concat([pd.read_parquet(item) for item in parquet_files], ignore_index=True)
    csv_files = sorted(path.rglob("*.csv"))
    if csv_files:
        return pd.concat([pd.read_csv(item, encoding="utf-8") for item in csv_files], ignore_index=True)
    raise ValueError(f"No candidate parquet/csv files found under: {path}")


def _required_columns_for_table(table_name: str, contract: dict[str, Any]) -> list[str]:
    if table_name == "silver_indicators":
        return list(SILVER_REQUIRED_COLUMNS)
    if table_name.startswith("gold_"):
        required = get_table_contract_columns(contract, "gold", table_name)
        return required or list(METADATA_NON_NULL_COLUMNS)
    required = get_table_contract_columns(contract, "analytics", table_name)
    if required:
        return required
    return list(FALLBACK_REQUIRED_COLUMNS.get(table_name, METADATA_NON_NULL_COLUMNS))


def _append_check(checks: list[dict[str, Any]], *, table: str, check: str, passed: bool, details: dict[str, Any]) -> None:
    checks.append(
        {
            "table": table,
            "check": check,
            "result": "PASSED" if passed else "FAILED",
            "details": details,
        }
    )


def run_candidate_data_quality_gate(
    *,
    expected_tables: list[str],
    candidate_artifacts: dict[str, Any],
    output_path: str | Path | None = None,
    contract_path: str | Path | None = None,
    contract_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract_payload or load_table_contract(contract_path or _default_contract_path())
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    checked_tables: list[str] = []

    expected_set = list(dict.fromkeys(expected_tables))
    for table_name in expected_set:
        exists = table_name in candidate_artifacts
        _append_check(
            checks,
            table=table_name,
            check="expected_table_presence",
            passed=exists,
            details={"expected": True, "exists": exists},
        )
        if not exists:
            errors.append(f"{table_name}: missing expected candidate artifact")
            continue

        try:
            frame = _load_candidate_frame(candidate_artifacts[table_name])
        except Exception as exc:
            _append_check(
                checks,
                table=table_name,
                check="artifact_loadable",
                passed=False,
                details={"error": str(exc)},
            )
            errors.append(f"{table_name}: unable to load candidate artifact ({exc})")
            continue

        checked_tables.append(table_name)
        _append_check(
            checks,
            table=table_name,
            check="artifact_loadable",
            passed=True,
            details={"row_count": int(len(frame)), "column_count": int(len(frame.columns))},
        )

        required_columns = _required_columns_for_table(table_name, contract)
        missing_columns = validate_required_columns(frame, required_columns)
        _append_check(
            checks,
            table=table_name,
            check="required_columns",
            passed=not missing_columns,
            details={"missing_columns": missing_columns},
        )
        if missing_columns:
            errors.append(f"{table_name}: missing required columns {missing_columns}")

        key_columns = SILVER_KEY_COLUMNS if table_name == "silver_indicators" else WAREHOUSE_KEY_COLUMNS
        duplicate_key_count = validate_no_duplicate_keys(frame, key_columns)
        duplicate_ok = duplicate_key_count == 0
        _append_check(
            checks,
            table=table_name,
            check="duplicate_keys",
            passed=duplicate_ok,
            details={"key_columns": list(key_columns), "duplicate_key_count": int(duplicate_key_count)},
        )
        if not duplicate_ok:
            errors.append(f"{table_name}: duplicate keys detected ({duplicate_key_count})")

        non_null_columns = list(SILVER_NON_NULL_CONTRACT_COLUMNS) if table_name == "silver_indicators" else [item for item in METADATA_NON_NULL_COLUMNS if item in frame.columns]
        null_counts = compute_null_counts(frame, non_null_columns)
        bad_nulls = {column: count for column, count in null_counts.items() if int(count) > 0}
        _append_check(
            checks,
            table=table_name,
            check="non_null_columns",
            passed=not bad_nulls,
            details={"null_counts": null_counts},
        )
        if bad_nulls:
            errors.append(f"{table_name}: non-null columns contain nulls {bad_nulls}")

        iso3_invalid_count = validate_country_code_iso3(frame)
        _append_check(
            checks,
            table=table_name,
            check="country_code_iso3",
            passed=iso3_invalid_count == 0,
            details={"invalid_count": int(iso3_invalid_count)},
        )
        if iso3_invalid_count != 0:
            errors.append(f"{table_name}: invalid ISO3 country_code ({iso3_invalid_count})")

        year_invalid_count = validate_year_range(frame)
        _append_check(
            checks,
            table=table_name,
            check="year_range",
            passed=year_invalid_count == 0,
            details={"invalid_count": int(year_invalid_count)},
        )
        if year_invalid_count != 0:
            errors.append(f"{table_name}: invalid year range ({year_invalid_count})")

        completeness_invalid_count = validate_completeness_score(frame)
        _append_check(
            checks,
            table=table_name,
            check="completeness_score_range",
            passed=completeness_invalid_count == 0,
            details={"invalid_count": int(completeness_invalid_count)},
        )
        if completeness_invalid_count != 0:
            errors.append(f"{table_name}: invalid completeness_score ({completeness_invalid_count})")

        crisis_invalid_counts = validate_crisis_columns(frame)
        bad_crisis = {key: int(value) for key, value in crisis_invalid_counts.items() if int(value) > 0}
        _append_check(
            checks,
            table=table_name,
            check="crisis_allowed_values",
            passed=not bad_crisis,
            details={"invalid_counts": crisis_invalid_counts},
        )
        if bad_crisis:
            errors.append(f"{table_name}: invalid crisis values {bad_crisis}")

    payload = {
        "status": "FAILED" if errors else "PASSED",
        "checks": checks,
        "errors": errors,
        "checked_tables": sorted(set(checked_tables)),
        "generated_at": utc_now_iso(),
    }

    if output_path is not None:
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return payload
