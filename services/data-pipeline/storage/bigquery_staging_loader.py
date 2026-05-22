from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from storage.bigquery_loader import load_parquet_to_bigquery


_SAFE_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_run_timestamp(value: str | None = None) -> str:
    raw = value or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cleaned = raw.strip().replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
    cleaned = re.sub(r"[^0-9_]", "", cleaned)

    if not cleaned:
        raise ValueError("run timestamp is empty after normalization.")

    return cleaned


def validate_table_name(table_name: str) -> str:
    cleaned = str(table_name or "").strip()

    if not cleaned:
        raise ValueError("table name is required.")

    if not _SAFE_TABLE_RE.match(cleaned):
        raise ValueError(
            f"Unsafe BigQuery table name: {cleaned!r}. "
            "Use only letters, numbers, and underscores."
        )

    return cleaned


def build_staging_table_name(
    production_table: str,
    run_timestamp: str | None = None,
) -> str:
    table = validate_table_name(production_table)
    timestamp = normalize_run_timestamp(run_timestamp)
    staging_table = f"{table}_staging_run_{timestamp}"
    return validate_table_name(staging_table)


def load_parquet_to_bigquery_staging(
    parquet_path: str | Path,
    project_id: str,
    dataset: str,
    production_table: str,
    *,
    run_timestamp: str | None = None,
    location: str | None = None,
) -> str:
    staging_table = build_staging_table_name(
        production_table=production_table,
        run_timestamp=run_timestamp,
    )

    return load_parquet_to_bigquery(
        parquet_path=parquet_path,
        project_id=project_id,
        dataset=dataset,
        table=staging_table,
        location=location,
        write_disposition="WRITE_TRUNCATE",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load local Parquet into a BigQuery staging table."
    )
    parser.add_argument("--parquet-path", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--run-timestamp", default=None)
    parser.add_argument("--location", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    table_id = load_parquet_to_bigquery_staging(
        parquet_path=args.parquet_path,
        project_id=args.project_id,
        dataset=args.dataset,
        production_table=args.table,
        run_timestamp=args.run_timestamp,
        location=args.location,
    )

    print(f"staging_table={table_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
