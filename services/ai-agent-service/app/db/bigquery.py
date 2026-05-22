from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from typing import Any

from app.core.config import settings

try:
    from google.cloud import bigquery
except Exception:  # pragma: no cover - fallback for local tests without dependency
    bigquery = None


_SELECT_STAR_PATTERN = re.compile(r"\bselect\s+\*", re.IGNORECASE)


def _clean_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


@lru_cache(maxsize=1)
def get_bigquery_client():
    if bigquery is None:
        raise RuntimeError("google-cloud-bigquery is not installed")
    return bigquery.Client(project=settings.bigquery_project_id)


def _scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    return "STRING"


def _array_type(values: list[Any]) -> str:
    first = next((value for value in values if value is not None), None)
    if first is None:
        return "STRING"
    return _scalar_type(first)


def _build_query_parameters(params: dict[str, Any]) -> list[Any]:
    if bigquery is None:
        return []

    query_parameters: list[Any] = []
    for name, value in params.items():
        if value is None:
            continue

        if isinstance(value, (list, tuple)):
            filtered = [item for item in value if item is not None]
            if not filtered:
                continue
            query_parameters.append(
                bigquery.ArrayQueryParameter(name, _array_type(filtered), filtered)
            )
            continue

        query_parameters.append(
            bigquery.ScalarQueryParameter(name, _scalar_type(value), value)
        )

    return query_parameters


def run_bigquery_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    if _SELECT_STAR_PATTERN.search(query):
        raise ValueError("SELECT * is not allowed")

    client = get_bigquery_client()
    query_parameters = _build_query_parameters(params)
    job_config = bigquery.QueryJobConfig(
        use_legacy_sql=False,
        query_parameters=query_parameters,
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
    )
    query_job = client.query(
        query,
        job_config=job_config,
        location=settings.bigquery_location,
    )
    rows = query_job.result()
    return [
        {key: _clean_value(value) for key, value in dict(row).items()}
        for row in rows
    ]
