from __future__ import annotations

import glob
from pathlib import Path
from typing import Any


def resolve_parquet_files(path: str | Path) -> list[Path]:
    base = Path(path)

    if base.is_file():
        if base.suffix.lower() != ".parquet":
            raise ValueError(f"Expected a .parquet file, got: {base}")
        return [base]

    if not base.exists():
        raise FileNotFoundError(f"Parquet path does not exist: {base}")

    if not base.is_dir():
        raise ValueError(f"Parquet path must be a file or directory: {base}")

    files = sorted(Path(item) for item in glob.glob(str(base / "*.parquet")))

    if not files:
        raise FileNotFoundError(f"No .parquet files found in: {base}")

    return files


def build_table_id(
    project_id: str,
    dataset: str,
    table: str,
) -> str:
    clean_project_id = str(project_id or "").strip()
    clean_dataset = str(dataset or "").strip()
    clean_table = str(table or "").strip()

    if not clean_project_id:
        raise ValueError("project_id is required.")
    if not clean_dataset:
        raise ValueError("dataset is required.")
    if not clean_table:
        raise ValueError("table is required.")

    return f"{clean_project_id}.{clean_dataset}.{clean_table}"


def make_bigquery_client(
    project_id: str | None = None,
    location: str | None = None,
) -> Any:
    from google.cloud import bigquery

    kwargs: dict[str, str] = {}

    if project_id:
        kwargs["project"] = project_id

    if location:
        kwargs["location"] = location

    return bigquery.Client(**kwargs)


def load_parquet_to_bigquery(
    parquet_path: str | Path,
    project_id: str,
    dataset: str,
    table: str,
    *,
    location: str | None = None,
    write_disposition: str = "WRITE_TRUNCATE",
) -> str:
    from google.cloud import bigquery

    files = resolve_parquet_files(parquet_path)
    table_id = build_table_id(project_id, dataset, table)
    client = make_bigquery_client(project_id=project_id, location=location)

    for index, file_path in enumerate(files):
        current_write_disposition = (
            write_disposition
            if index == 0
            else bigquery.WriteDisposition.WRITE_APPEND
        )

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=current_write_disposition,
        )

        with file_path.open("rb") as file_obj:
            job = client.load_table_from_file(
                file_obj,
                table_id,
                job_config=job_config,
                location=location,
            )
            job.result()

    destination = client.get_table(table_id)
    print(f"loaded -> bigquery: {table_id} rows={destination.num_rows}")
    return table_id


def load_silver_parquet_to_bigquery(
    parquet_path: str | Path,
    project_id: str,
    table: str = "silver_indicators",
    *,
    dataset: str = "gov_ai_silver",
    location: str | None = None,
    write_disposition: str = "WRITE_TRUNCATE",
) -> str:
    return load_parquet_to_bigquery(
        parquet_path,
        project_id,
        dataset,
        table,
        location=location,
        write_disposition=write_disposition,
    )


def load_gold_parquet_to_bigquery(
    parquet_path: str | Path,
    project_id: str,
    table: str,
    *,
    dataset: str = "gov_ai_gold",
    location: str | None = None,
    write_disposition: str = "WRITE_TRUNCATE",
) -> str:
    return load_parquet_to_bigquery(
        parquet_path,
        project_id,
        dataset,
        table,
        location=location,
        write_disposition=write_disposition,
    )
