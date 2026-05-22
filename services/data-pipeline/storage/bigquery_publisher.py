from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from storage.bigquery_loader import build_table_id, make_bigquery_client
from storage.bigquery_staging_loader import validate_table_name


_SAFE_DATASET_RE = re.compile(r"^[A-Za-z0-9_]+$")
WRITE_TRUNCATE = "WRITE_TRUNCATE"


@dataclass(frozen=True)
class BigQueryPublishPlan:
    source_table_id: str
    destination_table_id: str
    write_disposition: str


@dataclass(frozen=True)
class BigQueryPublishResult:
    source_table_id: str
    destination_table_id: str
    write_disposition: str
    destination_row_count: int


def validate_dataset_name(dataset: str) -> str:
    cleaned = str(dataset or "").strip()

    if not cleaned:
        raise ValueError("dataset is required.")

    if not _SAFE_DATASET_RE.match(cleaned):
        raise ValueError(
            f"Unsafe BigQuery dataset name: {cleaned!r}. "
            "Use only letters, numbers, and underscores."
        )

    return cleaned


def build_publish_plan(
    project_id: str,
    dataset: str,
    staging_table: str,
    production_table: str,
) -> BigQueryPublishPlan:
    clean_project_id = str(project_id or "").strip()
    clean_dataset = validate_dataset_name(dataset)
    clean_staging_table = validate_table_name(staging_table)
    clean_production_table = validate_table_name(production_table)

    if not clean_project_id:
        raise ValueError("project_id is required.")

    if clean_staging_table == clean_production_table:
        raise ValueError("staging_table and production_table must be different.")

    return BigQueryPublishPlan(
        source_table_id=build_table_id(
            clean_project_id,
            clean_dataset,
            clean_staging_table,
        ),
        destination_table_id=build_table_id(
            clean_project_id,
            clean_dataset,
            clean_production_table,
        ),
        write_disposition=WRITE_TRUNCATE,
    )


def publish_bigquery_staging_to_production(
    project_id: str,
    dataset: str,
    staging_table: str,
    production_table: str,
    *,
    location: str | None = None,
) -> BigQueryPublishResult:
    from google.cloud import bigquery

    plan = build_publish_plan(
        project_id=project_id,
        dataset=dataset,
        staging_table=staging_table,
        production_table=production_table,
    )
    client = make_bigquery_client(project_id=project_id, location=location)
    job_config = bigquery.CopyJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    job = client.copy_table(
        plan.source_table_id,
        plan.destination_table_id,
        job_config=job_config,
        location=location,
    )
    job.result()

    destination = client.get_table(plan.destination_table_id)
    result = BigQueryPublishResult(
        source_table_id=plan.source_table_id,
        destination_table_id=plan.destination_table_id,
        write_disposition=plan.write_disposition,
        destination_row_count=int(destination.num_rows),
    )
    print(
        "published -> bigquery: "
        f"{result.source_table_id} -> {result.destination_table_id} "
        f"rows={result.destination_row_count}"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a BigQuery staging table to a production table."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--staging-table", required=True)
    parser.add_argument("--production-table", required=True)
    parser.add_argument("--location", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.dry_run:
        plan = build_publish_plan(
            project_id=args.project_id,
            dataset=args.dataset,
            staging_table=args.staging_table,
            production_table=args.production_table,
        )
        print(f"source_table_id={plan.source_table_id}")
        print(f"destination_table_id={plan.destination_table_id}")
        print(f"write_disposition={plan.write_disposition}")
        print("dry_run=true; no BigQuery job was started.")
        return 0

    result = publish_bigquery_staging_to_production(
        project_id=args.project_id,
        dataset=args.dataset,
        staging_table=args.staging_table,
        production_table=args.production_table,
        location=args.location,
    )
    print(f"production_table={result.destination_table_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
