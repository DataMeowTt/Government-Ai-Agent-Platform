from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.bigquery_loader import build_table_id, make_bigquery_client, resolve_parquet_files


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

GOLD_REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "run_id",
    "run_date",
    "loaded_at",
)

ANALYTICS_REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "run_id",
    "run_date",
    "loaded_at",
)

ANALYTICS_CLUSTER_REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "cluster_id",
    "latest_valid_year",
    "run_id",
    "run_date",
    "loaded_at",
)


@dataclass(frozen=True)
class BigQueryValidationResult:
    table_id: str
    local_rows: int
    bigquery_rows: int
    required_columns: tuple[str, ...]
    actual_columns: tuple[str, ...]
    missing_columns: tuple[str, ...]

    @property
    def row_count_matches(self) -> bool:
        return self.local_rows == self.bigquery_rows

    @property
    def schema_matches(self) -> bool:
        return not self.missing_columns

    @property
    def passed(self) -> bool:
        return self.row_count_matches and self.schema_matches


def infer_required_columns(dataset: str, table: str) -> tuple[str, ...]:
    clean_dataset = str(dataset or "").strip()
    clean_table = str(table or "").strip()

    if clean_dataset == "gov_ai_silver" or clean_table == "silver_indicators":
        return SILVER_REQUIRED_COLUMNS

    if clean_table == "analytics_clusters":
        return ANALYTICS_CLUSTER_REQUIRED_COLUMNS

    if clean_dataset == "gov_ai_analytics" or clean_table.startswith("analytics_"):
        return ANALYTICS_REQUIRED_COLUMNS

    if clean_dataset == "gov_ai_gold" or clean_table.startswith("gold_"):
        return GOLD_REQUIRED_COLUMNS

    return ()


def find_missing_columns(
    required_columns: tuple[str, ...] | list[str],
    actual_columns: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    actual = set(actual_columns)
    return tuple(column for column in required_columns if column not in actual)


def count_parquet_rows(parquet_path: str | Path) -> int:
    files = resolve_parquet_files(parquet_path)
    total = 0

    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency: pyarrow is required to count local Parquet rows."
        ) from exc

    for file_path in files:
        metadata = pq.ParquetFile(file_path).metadata
        total += int(metadata.num_rows)

    return total


def get_bigquery_table_info(
    project_id: str,
    dataset: str,
    table: str,
    *,
    location: str | None = None,
) -> tuple[str, int, tuple[str, ...]]:
    table_id = build_table_id(project_id, dataset, table)
    client = make_bigquery_client(project_id=project_id, location=location)
    table_obj = client.get_table(table_id)
    actual_columns = tuple(field.name for field in table_obj.schema)
    return table_id, int(table_obj.num_rows), actual_columns


def validate_bigquery_loaded_table(
    parquet_path: str | Path,
    project_id: str,
    dataset: str,
    table: str,
    *,
    required_columns: tuple[str, ...] | list[str] | None = None,
    location: str | None = None,
) -> BigQueryValidationResult:
    table_id, bigquery_rows, actual_columns = get_bigquery_table_info(
        project_id=project_id,
        dataset=dataset,
        table=table,
        location=location,
    )
    local_rows = count_parquet_rows(parquet_path)

    required = tuple(required_columns or infer_required_columns(dataset, table))
    missing_columns = find_missing_columns(required, actual_columns)

    return BigQueryValidationResult(
        table_id=table_id,
        local_rows=local_rows,
        bigquery_rows=bigquery_rows,
        required_columns=required,
        actual_columns=actual_columns,
        missing_columns=missing_columns,
    )


def parse_required_columns(raw_value: str | None) -> tuple[str, ...] | None:
    if raw_value is None:
        return None

    columns = tuple(
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    )

    return columns or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate BigQuery staging table row count and minimal schema."
    )
    parser.add_argument("--parquet-path", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--location", default=None)
    parser.add_argument(
        "--required-columns",
        default=None,
        help="Optional comma-separated required columns. If omitted, infer by dataset/table.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_bigquery_loaded_table(
        parquet_path=args.parquet_path,
        project_id=args.project_id,
        dataset=args.dataset,
        table=args.table,
        required_columns=parse_required_columns(args.required_columns),
        location=args.location,
    )

    print(f"table_id={result.table_id}")
    print(f"local_rows={result.local_rows}")
    print(f"bigquery_rows={result.bigquery_rows}")
    print(f"row_count_matches={result.row_count_matches}")
    print(f"required_columns={list(result.required_columns)}")
    print(f"missing_columns={list(result.missing_columns)}")
    print(f"schema_matches={result.schema_matches}")

    if not result.passed:
        raise SystemExit(1)

    print("PASS: BigQuery staging validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
