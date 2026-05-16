import traceback

from src.core.config import get_runtime_metadata, settings
from src.core.logger import logger
from src.adapters.factory import get_analytics_adapter
from src.generated.indicator_contract import (
    INDICATORS_FOR_CLUSTER,
    PUBLIC_INDICATORS,
    TABLES_INDICATORS,
)

BASELINE_CLUSTER_YEARS = (2000, 2010, 2020)
MIN_LATEST_VALID_YEAR = 2020
MAX_LATEST_VALID_YEAR = 2030


def _build_indicator_tasks(table: str | None = None, indicator: str | None = None) -> list[dict]:
    tasks = []

    for table_name, indicators in TABLES_INDICATORS.items():
        if table and table_name != table:
            continue

        for indicator_code in indicators:
            if indicator and indicator_code != indicator:
                continue
            tasks.append({"table": table_name, "indicator": indicator_code})

    return tasks


def _build_summary(
    dry_run: bool,
    target: str,
    metadata: dict[str, str],
    indicator_tasks: list[dict],
    cluster_years: list[int],
    skip_clusters: bool,
    latest_valid_year: int | None,
    warnings: list[str],
) -> dict:
    return {
        "target": target,
        "dry_run": dry_run,
        "run_id": metadata["run_id"],
        "run_date": metadata["run_date"],
        "loaded_at": metadata["loaded_at"],
        "metadata": metadata,
        "latest_valid_year": latest_valid_year,
        "resolved_cluster_years": [] if skip_clusters else cluster_years,
        "warnings": warnings,
        "planned": {
            "indicator_tasks": len(indicator_tasks),
            "cluster_tasks": 0 if skip_clusters else len(cluster_years),
        },
        "executed": {
            "indicator_tasks": 0,
            "cluster_tasks": 0,
        },
        "skipped": {
            "indicator_tasks": 0,
            "cluster_tasks": len(cluster_years) if skip_clusters else 0,
        },
        "errors": [],
    }


def _build_adapter_plans(
    adapter,
    indicator_tasks: list[dict],
    cluster_years: list[int],
    skip_clusters: bool,
    dry_run: bool,
    latest_valid_year: int | None,
) -> dict:
    indicators_by_table: dict[str, list[str]] = {}
    for task in indicator_tasks:
        indicators_by_table.setdefault(task["table"], []).append(task["indicator"])

    plans = {
        "indicators": [
            adapter.build_indicator_plan(
                source_table=table_name,
                indicators=indicators,
                dry_run=dry_run,
            ).to_dict()
            for table_name, indicators in indicators_by_table.items()
        ],
        "clusters": [],
    }

    if not skip_clusters:
        plans["clusters"].append(
            adapter.build_cluster_plan(
                cluster_years=cluster_years,
                dry_run=dry_run,
                latest_valid_year=latest_valid_year,
            ).to_dict()
        )

    return plans


def validate_latest_valid_year(value: int | str | None) -> int | None:
    if value is None:
        return None

    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"latest_valid_year must be an integer, got: {value!r}") from exc

    if year < 1980 or year > MAX_LATEST_VALID_YEAR:
        raise ValueError(
            f"latest_valid_year must be between 1980 and {MAX_LATEST_VALID_YEAR}, got: {year}"
        )

    if year < MIN_LATEST_VALID_YEAR:
        raise ValueError(
            f"latest_valid_year must be at least {MIN_LATEST_VALID_YEAR}, got: {year}"
        )

    return year


def validate_cluster_year(value: int | str | None) -> int:
    if value is None:
        raise ValueError("cluster year is required.")

    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cluster year must be an integer, got: {value!r}") from exc

    if year < 1980 or year > MAX_LATEST_VALID_YEAR:
        raise ValueError(f"cluster year must be between 1980 and {MAX_LATEST_VALID_YEAR}, got: {year}")

    return year


def resolve_cluster_target_years(
    latest_valid_year: int | str | None = None,
    cluster_years: list[int] | None = None,
) -> list[int]:
    if cluster_years is not None:
        return sorted({validate_cluster_year(year) for year in cluster_years})

    resolved = set(BASELINE_CLUSTER_YEARS)
    valid_latest_year = validate_latest_valid_year(latest_valid_year)
    if valid_latest_year is not None:
        resolved.add(valid_latest_year)

    return sorted(resolved)


def _latest_year_from_settings() -> int | None:
    return validate_latest_valid_year(settings.ANALYTICS_LATEST_VALID_YEAR)


def _gold_table_for_cluster_indicator(indicator: str) -> str:
    indicator_meta = PUBLIC_INDICATORS.get(indicator)
    gold_table = indicator_meta.get("gold_table") if indicator_meta else None

    if not gold_table:
        raise ValueError(f"Table not found for cluster indicator: {indicator}")

    return str(gold_table)


def determine_latest_valid_year_from_postgres() -> int | None:
    from sqlalchemy import text

    from src.core.database import get_engine

    engine = get_engine()
    max_years: list[int] = []

    with engine.connect() as conn:
        for indicator in INDICATORS_FOR_CLUSTER:
            table_name = _gold_table_for_cluster_indicator(indicator)
            result = conn.execute(
                text(
                    f"""
                    SELECT MAX(year) AS latest_year
                    FROM {table_name}
                    WHERE "{indicator}" IS NOT NULL
                    """
                )
            ).scalar()

            if result is not None:
                max_years.append(int(result))

    if not max_years:
        return None

    return validate_latest_valid_year(max(max_years))


def _resolve_latest_valid_year(
    *,
    explicit_latest_valid_year: int | None,
    target: str,
    dry_run: bool,
    warnings: list[str],
) -> int | None:
    if explicit_latest_valid_year is not None:
        return validate_latest_valid_year(explicit_latest_valid_year)

    configured_latest_year = _latest_year_from_settings()
    if configured_latest_year is not None:
        return configured_latest_year

    if target == "postgres" and not dry_run:
        latest_year = determine_latest_valid_year_from_postgres()
        if latest_year is not None:
            return latest_year

        warnings.append("latest_valid_year could not be derived from postgres source data.")
        return None

    warnings.append(
        "latest_valid_year could not be derived offline; provide --latest-valid-year "
        "or ANALYTICS_LATEST_VALID_YEAR to include a latest-year cluster task."
    )
    return None


def run_all_analytics(
    target: str = "postgres",
    dry_run: bool = False,
    table: str | None = None,
    indicator: str | None = None,
    skip_clusters: bool = False,
    cluster_years: list[int] | None = None,
    n_clusters: int = 5,
    runtime_metadata: dict[str, str] | None = None,
    project_id: str | None = None,
    dataset: str | None = None,
    location: str | None = None,
    latest_valid_year: int | None = None,
) -> dict:
    adapter = get_analytics_adapter(
        target,
        project_id=project_id,
        dataset=dataset or settings.BIGQUERY_ANALYTICS_DATASET,
        location=location or settings.BIGQUERY_LOCATION,
    )
    adapter.ensure_can_execute(dry_run=dry_run)

    if table and table not in TABLES_INDICATORS:
        raise ValueError(f"Unknown analytics source table: {table}")

    if indicator and not any(indicator in indicators for indicators in TABLES_INDICATORS.values()):
        raise ValueError(f"Unknown analytics indicator: {indicator}")

    warnings: list[str] = []
    resolved_latest_valid_year = _resolve_latest_valid_year(
        explicit_latest_valid_year=latest_valid_year,
        target=adapter.target,
        dry_run=dry_run,
        warnings=warnings,
    )
    indicator_tasks = _build_indicator_tasks(table=table, indicator=indicator)
    selected_cluster_years = resolve_cluster_target_years(
        latest_valid_year=resolved_latest_valid_year,
        cluster_years=cluster_years,
    )
    metadata = runtime_metadata or get_runtime_metadata()
    summary = _build_summary(
        dry_run=dry_run,
        target=target,
        metadata=metadata,
        indicator_tasks=indicator_tasks,
        cluster_years=selected_cluster_years,
        skip_clusters=skip_clusters,
        latest_valid_year=resolved_latest_valid_year,
        warnings=warnings,
    )

    logger.info(
        "Starting analytics batch: target=%s dry_run=%s indicator_tasks=%s cluster_tasks=%s",
        adapter.target,
        dry_run,
        len(indicator_tasks),
        0 if skip_clusters else len(selected_cluster_years),
    )

    summary["write_plans"] = _build_adapter_plans(
        adapter=adapter,
        indicator_tasks=indicator_tasks,
        cluster_years=selected_cluster_years,
        skip_clusters=skip_clusters,
        dry_run=dry_run,
        latest_valid_year=resolved_latest_valid_year,
    )

    if dry_run:
        summary["planned_tasks"] = {
            "indicators": indicator_tasks,
            "clusters": [] if skip_clusters else selected_cluster_years,
        }
        logger.info("Analytics dry-run completed without database access")
        return summary

    import pandas as pd

    if adapter.target != "postgres":
        raise RuntimeError(f"Live analytics execution is not implemented for target={adapter.target}")

    from src.pipelines.anomaly import update_anomaly_scores
    from src.pipelines.cluster import run_clustering
    from src.pipelines.trend import compute_trend_for_indicator, save_trends_to_analytics

    for task in indicator_tasks:
        table_name = task["table"]
        indicator_code = task["indicator"]
        logger.info(f"Batch Processing: {indicator_code} in {table_name}")
        try:
            results = compute_trend_for_indicator(table_name, indicator_code)
            if results:
                df = pd.DataFrame(results)
                save_trends_to_analytics(table_name, indicator_code, df, runtime_metadata=metadata)
                update_anomaly_scores(table_name, indicator_code, runtime_metadata=metadata)
            else:
                summary["skipped"]["indicator_tasks"] += 1
            summary["executed"]["indicator_tasks"] += 1
        except Exception as e:
            error = {
                "kind": "indicator",
                "table": table_name,
                "indicator": indicator_code,
                "error": str(e),
            }
            summary["errors"].append(error)
            logger.error(f"Error processing {indicator_code} in {table_name}: {traceback.format_exc()}")

    if not skip_clusters:
        for year in selected_cluster_years:
            logger.info(f"Batch Processing Clustering for year {year}")
            try:
                run_clustering(
                    target_year=year,
                    n_clusters=n_clusters,
                    runtime_metadata=metadata,
                    latest_valid_year=resolved_latest_valid_year,
                )
                summary["executed"]["cluster_tasks"] += 1
            except Exception as e:
                error = {
                    "kind": "cluster",
                    "year": year,
                    "error": str(e),
                }
                summary["errors"].append(error)
                logger.error(f"Error processing clustering for {year}: {traceback.format_exc()}")

    logger.info("Full Analytics Batch Process Completed")
    return summary
