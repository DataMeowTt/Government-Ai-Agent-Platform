from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gold.tables import crisis_risk, fiscal_monetary, growth_dynamics, social_welfare, structural_composition
from warehouse.bigquery_warehouse_validation import (
    ALLOWED_SOURCES,
    SILVER_NON_NULL_CONTRACT_COLUMNS,
    SILVER_REQUIRED_COLUMNS,
    compute_null_counts,
    get_table_contract_columns,
    load_table_contract,
    parse_table_id,
    summarize_dataframe_validation,
    validate_completeness_score,
    validate_country_code_iso3,
    validate_crisis_columns,
    validate_year_range,
)


DEFAULT_MAX_VALIDATION_BYTES = 1_000_000_000
DEFAULT_OUTPUT_DIR = "../../tmp/bigquery_warehouse_rebuild"
DEFAULT_SILVER_TABLE = "western-pivot-452008-a6.gov_ai_silver.silver_indicators"
EXPECTED_SILVER_ROW_COUNT = 280210
REQUIRED_SILVER_COLUMNS = list(SILVER_REQUIRED_COLUMNS)
REQUIRED_SILVER_NON_NULL_COLUMNS = list(SILVER_NON_NULL_CONTRACT_COLUMNS)
GOLD_TABLE_NAMES = (
    "gold_growth_dynamics",
    "gold_fiscal_monetary",
    "gold_crisis_risk",
    "gold_social_welfare",
    "gold_structural_composition",
)
ANALYTICS_TABLE_NAMES = (
    "analytics_gold_growth_dynamics",
    "analytics_gold_fiscal_monetary",
    "analytics_gold_crisis_risk",
    "analytics_gold_social_welfare",
    "analytics_gold_structural_composition",
    "analytics_clusters",
)
CLUSTER_BASELINE_YEARS = (2000, 2010, 2020)


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    candidates = [current.parent, *current.parents]
    for candidate in candidates:
        if (candidate / "contracts" / "table_contract.yaml").exists():
            return candidate
    raise FileNotFoundError(
        "Unable to resolve repository root containing contracts/table_contract.yaml "
        f"from {current}"
    )


@dataclass(frozen=True)
class RuntimeMetadata:
    run_id: str
    run_date: datetime.date
    loaded_at: datetime


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class BigQueryExecutor:
    def __init__(self, *, project_id: str, location: str) -> None:
        self.project_id = project_id
        self.location = location
        self.backend = "python_client"
        self._client: Any | None = None
        self._bq_executable: str | None = None
        try:
            from google.auth.exceptions import DefaultCredentialsError
            from google.cloud import bigquery
        except Exception:
            self._activate_cli_backend()
            return

        try:
            self._client = bigquery.Client(project=project_id, location=location)
        except Exception as exc:  # pragma: no cover - depends on local ADC configuration
            if exc.__class__.__name__ != "DefaultCredentialsError":
                raise
            _ = DefaultCredentialsError
            self._activate_cli_backend()

    def _activate_cli_backend(self) -> None:
        executable = shutil.which("bq.cmd") or shutil.which("bq")
        if not executable:
            raise RuntimeError("Unable to find bq executable on PATH.")
        self.backend = "bq_cli"
        self._bq_executable = executable
        self._client = None

    def _run_bq(self, args: list[str], *, json_output: bool = False) -> str:
        if not self._bq_executable:
            raise RuntimeError("bq executable is not configured.")
        command = [
            self._bq_executable,
            "--quiet=true",
            f"--location={self.location}",
        ]
        if json_output:
            command.append("--format=json")
        command.extend(args)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                "bq command failed: "
                f"args={args!r} stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}"
            )
        return result.stdout

    @staticmethod
    def _to_bq_table_ref(table_id: str) -> str:
        project, dataset, table = parse_table_id(table_id)
        return f"{project}:{dataset}.{table}"

    def table_exists(self, table_id: str) -> bool:
        if self.backend == "python_client":
            try:
                self._client.get_table(table_id)
                return True
            except Exception:
                return False
        try:
            self._run_bq(["show", self._to_bq_table_ref(table_id)])
            return True
        except Exception:
            return False

    def query_dataframe(self, query: str, *, max_bytes_billed: int | None = None) -> pd.DataFrame:
        if self.backend == "python_client":
            from google.cloud import bigquery

            job_config = bigquery.QueryJobConfig(
                maximum_bytes_billed=max_bytes_billed,
                use_legacy_sql=False,
            )
            job = self._client.query(query, location=self.location, job_config=job_config)
            return job.to_dataframe(create_bqstorage_client=False)

        args = ["query", "--nouse_legacy_sql"]
        if max_bytes_billed:
            args.append(f"--maximum_bytes_billed={int(max_bytes_billed)}")
        args.extend(["--max_rows=2000000", "--format=csv", query])
        raw_csv = self._run_bq(args)
        return pd.read_csv(io.StringIO(raw_csv))

    def query_scalar_int(self, query: str, *, max_bytes_billed: int | None = None) -> int:
        df = self.query_dataframe(query, max_bytes_billed=max_bytes_billed)
        if df.empty:
            return 0
        return int(df.iloc[0, 0])


def get_active_gcloud_project() -> str:
    for env_name in ("GOOGLE_CLOUD_PROJECT", "PROJECT_ID", "GCLOUD_PROJECT"):
        env_value = str(os.environ.get(env_name) or "").strip()
        if env_value:
            return env_value

    executable = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not executable:
        raise RuntimeError("Unable to find gcloud executable on PATH.")
    result = subprocess.run(
        [executable, "config", "get-value", "project"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to read active gcloud project: {result.stderr.strip()}")
    return result.stdout.strip()


def require_active_project(project_id: str) -> str:
    active = get_active_gcloud_project()
    if active != project_id:
        raise RuntimeError(f"Active gcloud project mismatch: expected={project_id!r} actual={active!r}")
    return active


def run_silver_preflight(
    *,
    executor: BigQueryExecutor,
    silver_table_id: str,
    expected_row_count: int | None = None,
    required_columns: list[str] | None = None,
    non_null_columns: list[str] | None = None,
    max_validation_bytes: int = DEFAULT_MAX_VALIDATION_BYTES,
) -> dict[str, Any]:
    required = required_columns or list(REQUIRED_SILVER_COLUMNS)
    non_null = non_null_columns or list(REQUIRED_SILVER_NON_NULL_COLUMNS)
    project_id, dataset, table = parse_table_id(silver_table_id)

    exists = executor.table_exists(silver_table_id)
    if not exists:
        raise ValueError(f"Silver table not found: {silver_table_id}")

    schema_query = (
        f"SELECT column_name, is_nullable, data_type "
        f"FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS` "
        f"WHERE table_name = '{table}' "
        "ORDER BY ordinal_position"
    )
    schema_df = executor.query_dataframe(schema_query, max_bytes_billed=max_validation_bytes)
    schema_modes = {
        str(row["column_name"]): ("NULLABLE" if str(row["is_nullable"]).upper() == "YES" else "REQUIRED")
        for _, row in schema_df.iterrows()
    }
    missing_columns = [column for column in required if column not in schema_modes]
    if missing_columns:
        raise ValueError(f"Silver table missing required columns: {missing_columns}")

    row_count = executor.query_scalar_int(
        f"SELECT COUNT(*) FROM `{silver_table_id}`",
        max_bytes_billed=max_validation_bytes,
    )
    if expected_row_count is not None and row_count != expected_row_count:
        raise ValueError(f"Silver row_count mismatch: expected={expected_row_count} actual={row_count}")
    if row_count <= 0:
        raise ValueError(f"Silver row_count must be > 0 for scheduled validation: actual={row_count}")

    null_expr = ", ".join(
        f"SUM(CASE WHEN `{column}` IS NULL THEN 1 ELSE 0 END) AS `{column}`"
        for column in non_null
    )
    null_df = executor.query_dataframe(
        f"SELECT {null_expr} FROM `{silver_table_id}`",
        max_bytes_billed=max_validation_bytes,
    )
    null_counts = {column: int(null_df.iloc[0][column]) for column in non_null}
    bad_nulls = {column: value for column, value in null_counts.items() if value > 0}
    if bad_nulls:
        raise ValueError(f"Silver non-null contract violated: {bad_nulls}")

    source_df = executor.query_dataframe(
        f"SELECT source, COUNT(*) AS row_count FROM `{silver_table_id}` GROUP BY source ORDER BY source",
        max_bytes_billed=max_validation_bytes,
    )
    source_counts = {str(row["source"]): int(row["row_count"]) for _, row in source_df.iterrows()}
    invalid_sources = sorted(set(source_counts) - set(ALLOWED_SOURCES))
    if invalid_sources:
        raise ValueError(f"Silver contains unsupported source values: {invalid_sources}")

    stats_df = executor.query_dataframe(
        "SELECT "
        "MIN(year) AS year_min, "
        "MAX(year) AS year_max, "
        "COUNT(DISTINCT country_code) AS country_count, "
        "COUNT(DISTINCT indicator) AS indicator_count "
        f"FROM `{silver_table_id}`",
        max_bytes_billed=max_validation_bytes,
    )
    stats = {
        "year_min": int(stats_df.iloc[0]["year_min"]),
        "year_max": int(stats_df.iloc[0]["year_max"]),
        "country_count": int(stats_df.iloc[0]["country_count"]),
        "indicator_count": int(stats_df.iloc[0]["indicator_count"]),
    }

    return {
        "table_exists": exists,
        "silver_table_id": silver_table_id,
        "row_count": row_count,
        "expected_row_count": expected_row_count,
        "dynamic_row_count_validation": expected_row_count is None,
        "required_columns": required,
        "required_column_schema_modes": {column: schema_modes[column] for column in required},
        "null_counts_non_null_contract_columns": null_counts,
        "allowed_sources": list(ALLOWED_SOURCES),
        "source_counts": source_counts,
        **stats,
    }


def fetch_silver_dataframe(
    *,
    executor: BigQueryExecutor,
    silver_table_id: str,
    output_dir: Path,
    max_bytes_billed: int = DEFAULT_MAX_VALIDATION_BYTES,
) -> pd.DataFrame:
    query = (
        "SELECT country_code, country, year, indicator, value, source, run_id, run_date, loaded_at "
        f"FROM `{silver_table_id}` "
        "ORDER BY country_code, year, indicator, source"
    )
    frame = executor.query_dataframe(query, max_bytes_billed=max_bytes_billed)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
    frame["run_date"] = pd.to_datetime(frame["run_date"], errors="coerce").dt.date
    frame["loaded_at"] = pd.to_datetime(frame["loaded_at"], errors="coerce")
    silver_dir = _ensure_dir(output_dir / "silver_extract")
    frame.to_parquet(silver_dir / "part-00000.parquet", index=False)
    return frame


def derive_runtime_metadata(silver_df: pd.DataFrame) -> RuntimeMetadata:
    run_id_series = silver_df["run_id"].dropna().astype(str)
    if run_id_series.empty:
        run_id = "bigquery_warehouse_rebuild"
    else:
        run_id = run_id_series.mode().iloc[0]

    run_date_series = pd.to_datetime(silver_df["run_date"], errors="coerce").dropna()
    run_date = run_date_series.max().date() if not run_date_series.empty else _utc_now_naive().date()

    loaded_at_series = pd.to_datetime(silver_df["loaded_at"], errors="coerce").dropna()
    loaded_at = loaded_at_series.max().to_pydatetime().replace(tzinfo=None) if not loaded_at_series.empty else _utc_now_naive()

    return RuntimeMetadata(run_id=run_id, run_date=run_date, loaded_at=loaded_at)


def _add_runtime_metadata(df: pd.DataFrame, metadata: RuntimeMetadata) -> pd.DataFrame:
    result = df.copy()
    result["run_id"] = metadata.run_id
    result["run_date"] = metadata.run_date
    result["loaded_at"] = metadata.loaded_at
    return result


def _collapse_duplicate_country_year_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "country_code" not in df.columns or "year" not in df.columns:
        return df
    if int(df.duplicated(subset=["country_code", "year"]).sum()) == 0:
        return df

    sorted_df = df.copy()
    if "completeness_score" in sorted_df.columns:
        sorted_df = sorted_df.sort_values(
            ["country_code", "year", "completeness_score"],
            ascending=[True, True, False],
        )
    else:
        sorted_df = sorted_df.sort_values(["country_code", "year"])

    def _coalesce(series: pd.Series) -> Any:
        non_null = series.dropna()
        return non_null.iloc[0] if not non_null.empty else np.nan

    grouped = (
        sorted_df.groupby(["country_code", "year"], as_index=False, sort=False)
        .agg(_coalesce)
        .reset_index(drop=True)
    )
    return grouped


def _validate_gold_table(
    *,
    table_name: str,
    table_df: pd.DataFrame,
    required_columns: list[str],
) -> dict[str, Any]:
    summary = summarize_dataframe_validation(
        df=table_df,
        table_name=table_name,
        required_columns=required_columns,
        key_columns=("country_code", "year"),
    )
    iso3_invalid_count = validate_country_code_iso3(table_df)
    year_invalid_count = validate_year_range(table_df)
    completeness_out_of_range_count = validate_completeness_score(table_df)
    crisis_invalid_counts = validate_crisis_columns(table_df)

    if summary.row_count <= 0:
        raise ValueError(f"{table_name} is empty.")
    if summary.duplicate_key_count != 0:
        raise ValueError(f"{table_name} duplicate country/year keys: {summary.duplicate_key_count}")
    if summary.missing_columns:
        raise ValueError(f"{table_name} missing required columns: {summary.missing_columns}")
    if iso3_invalid_count:
        raise ValueError(f"{table_name} invalid ISO3 country_code count: {iso3_invalid_count}")
    if year_invalid_count:
        raise ValueError(f"{table_name} invalid year range count: {year_invalid_count}")
    if completeness_out_of_range_count:
        raise ValueError(
            f"{table_name} completeness_score out of [0,1]: {completeness_out_of_range_count}"
        )
    bad_crisis = {key: value for key, value in crisis_invalid_counts.items() if value > 0}
    if bad_crisis:
        raise ValueError(f"{table_name} invalid crisis flag values: {bad_crisis}")

    return {
        "table_name": table_name,
        "row_count": summary.row_count,
        "column_count": summary.column_count,
        "duplicate_key_count": summary.duplicate_key_count,
        "iso3_invalid_count": iso3_invalid_count,
        "year_invalid_count": year_invalid_count,
        "completeness_out_of_range_count": completeness_out_of_range_count,
        "crisis_invalid_counts": crisis_invalid_counts,
        "missing_columns": summary.missing_columns,
    }


def build_gold_tables(
    *,
    silver_df: pd.DataFrame,
    metadata: RuntimeMetadata,
    contract: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    table_builders = {
        "gold_growth_dynamics": growth_dynamics.build,
        "gold_fiscal_monetary": fiscal_monetary.build,
        "gold_crisis_risk": crisis_risk.build,
        "gold_social_welfare": social_welfare.build,
        "gold_structural_composition": structural_composition.build,
    }
    gold_output = _ensure_dir(output_dir / "gold")
    built_tables: dict[str, pd.DataFrame] = {}
    summaries: list[dict[str, Any]] = []

    for table_name, builder in table_builders.items():
        built = builder(silver_df)
        built = _collapse_duplicate_country_year_rows(built)
        built = _add_runtime_metadata(built, metadata)
        built = built.sort_values(["country_code", "year"]).reset_index(drop=True)
        required_columns = get_table_contract_columns(contract, "gold", table_name)
        table_summary = _validate_gold_table(
            table_name=table_name,
            table_df=built,
            required_columns=required_columns,
        )
        destination = _ensure_dir(gold_output / table_name)
        built.to_parquet(destination / "part-00000.parquet", index=False)
        table_summary["parquet_path"] = str((destination / "part-00000.parquet").resolve())
        summaries.append(table_summary)
        built_tables[table_name] = built

    return built_tables, summaries


def _load_indicator_contract_module(repo_root: Path) -> Any:
    worker_root = repo_root / "services" / "analytics-worker"
    if worker_root.exists():
        if str(worker_root) not in sys.path:
            sys.path.insert(0, str(worker_root))
        try:
            from src.generated import indicator_contract  # type: ignore

            return indicator_contract
        except Exception:
            pass

    class _FallbackIndicatorContract:
        TABLES_INDICATORS = {
            "gold_growth_dynamics": ["GDP_growth_YoY", "GDP_pc_growth_gap", "rGDP_growth_YoY", "rolling_mean_5yr", "trend_deviation"],
            "gold_fiscal_monetary": ["fiscal_balance_GDP", "govdebt_GDP", "inflation_cpi", "inflation_gap", "real_interest_rate", "tax_revenue_pct_GDP"],
            "gold_crisis_risk": ["REER_deviation", "spending_efficiency"],
            "gold_social_welfare": ["hcons_growth", "poverty_change_5yr", "poverty_headcount", "unemployment_total", "youth_unemployment_gap"],
            "gold_structural_composition": ["GFCF_to_GDP", "GNI_to_GDP", "agri_va_share", "food_bev_share_manuf", "manuf_va_share"],
        }
        INDICATORS_FOR_CLUSTER = [
            "GFCF_to_GDP",
            "GNI_to_GDP",
            "agri_va_share",
            "manuf_va_share",
            "poverty_headcount",
            "unemployment_total",
            "urban_pop_pct",
        ]
        PUBLIC_INDICATORS = {
            "GFCF_to_GDP": {"gold_table": "gold_structural_composition"},
            "GNI_to_GDP": {"gold_table": "gold_structural_composition"},
            "agri_va_share": {"gold_table": "gold_structural_composition"},
            "manuf_va_share": {"gold_table": "gold_structural_composition"},
            "poverty_headcount": {"gold_table": "gold_social_welfare"},
            "unemployment_total": {"gold_table": "gold_social_welfare"},
            "urban_pop_pct": {"gold_table": "gold_social_welfare"},
        }

    return _FallbackIndicatorContract


def _compute_trend_and_anomaly_for_indicator(df: pd.DataFrame, indicator: str) -> pd.DataFrame:
    required_cols = ["country_code", "country", "year", indicator]
    subset = df[required_cols].dropna(subset=[indicator]).copy()
    if subset.empty:
        return pd.DataFrame(columns=["country_code", "country", "year"])

    rows: list[dict[str, Any]] = []
    for country_code, group in subset.groupby("country_code"):
        group = group.sort_values("year")
        if len(group) < 3:
            continue
        x = group["year"].to_numpy(dtype=float)
        y = pd.to_numeric(group[indicator], errors="coerce").to_numpy(dtype=float)
        if np.isnan(y).all():
            continue
        slope, intercept = np.polyfit(x, y, 1)
        trend = slope * x + intercept
        residual = y - trend
        denom = float(np.sum((y - y.mean()) ** 2))
        r2 = 0.0 if denom <= 0 else float(1.0 - np.sum((y - trend) ** 2) / denom)
        if len(residual) < 5:
            anomaly_scores = np.zeros(len(residual), dtype=float)
        else:
            std = float(np.std(residual))
            if std <= 0:
                anomaly_scores = np.zeros(len(residual), dtype=float)
            else:
                raw = np.abs((residual - float(np.mean(residual))) / std)
                min_v = float(np.min(raw))
                max_v = float(np.max(raw))
                anomaly_scores = np.zeros(len(raw), dtype=float) if max_v - min_v <= 0 else (raw - min_v) / (max_v - min_v)
        for idx, (_, row) in enumerate(group.iterrows()):
            rows.append(
                {
                    "country_code": country_code,
                    "country": row["country"],
                    "year": int(row["year"]),
                    f"{indicator}_actual": float(y[idx]),
                    f"{indicator}_trend": float(trend[idx]),
                    f"{indicator}_residual": float(residual[idx]),
                    f"{indicator}_slope": float(slope),
                    f"{indicator}_intercept": float(intercept),
                    f"{indicator}_r2": float(r2),
                    f"{indicator}_anomaly_score": float(anomaly_scores[idx]),
                }
            )
    return pd.DataFrame(rows)


def _build_analytics_table_from_gold(
    *,
    gold_df: pd.DataFrame,
    indicators: list[str],
    metadata: RuntimeMetadata,
) -> pd.DataFrame:
    keys = gold_df[["country_code", "country", "year"]].drop_duplicates().copy()
    result = keys.sort_values(["country_code", "year"]).reset_index(drop=True)
    for indicator in indicators:
        if indicator not in gold_df.columns:
            for suffix in ("_actual", "_trend", "_residual", "_slope", "_intercept", "_r2", "_anomaly_score"):
                result[f"{indicator}{suffix}"] = np.nan
            continue
        indicator_df = _compute_trend_and_anomaly_for_indicator(gold_df, indicator)
        if indicator_df.empty:
            for suffix in ("_actual", "_trend", "_residual", "_slope", "_intercept", "_r2", "_anomaly_score"):
                result[f"{indicator}{suffix}"] = np.nan
            continue
        keep_cols = [column for column in indicator_df.columns if column not in {"country"}]
        result = result.merge(indicator_df[keep_cols], on=["country_code", "year"], how="left")
    return _add_runtime_metadata(result, metadata)


def _build_clusters(
    *,
    gold_tables: dict[str, pd.DataFrame],
    cluster_indicators: list[str],
    public_indicators: dict[str, dict[str, Any]],
    metadata: RuntimeMetadata,
) -> pd.DataFrame:
    frames = []
    for indicator in cluster_indicators:
        meta = public_indicators.get(indicator) or {}
        table_name = str(meta.get("gold_table") or "")
        if not table_name or table_name not in gold_tables:
            continue
        source_df = gold_tables[table_name]
        if indicator not in source_df.columns:
            continue
        frames.append(
            source_df[["country_code", "country", "year", indicator]].copy()
        )
    if not frames:
        return pd.DataFrame(columns=["country_code", "country", "year", "cluster_id", "latest_valid_year"])

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on=["country_code", "country", "year"], how="outer")
    merged = merged.sort_values(["country_code", "year"]).reset_index(drop=True)
    merged[cluster_indicators] = merged.groupby("country_code")[cluster_indicators].ffill(limit=2)
    latest_valid_year = int(pd.to_numeric(merged["year"], errors="coerce").max())
    target_years = sorted(set(CLUSTER_BASELINE_YEARS + (latest_valid_year,)))

    outputs: list[pd.DataFrame] = []
    threshold = max(1, int(np.ceil(0.7 * len(cluster_indicators))))
    for target_year in target_years:
        target = merged[merged["year"] == target_year].copy()
        if target.empty:
            continue
        target = target.dropna(subset=cluster_indicators, thresh=threshold)
        if target.empty:
            continue
        values = target[cluster_indicators].copy()
        values = values.apply(pd.to_numeric, errors="coerce")
        values = values.fillna(values.mean())
        values = values.fillna(0.0)
        standardized = (values - values.mean()) / values.std(ddof=0).replace(0.0, 1.0)
        score = standardized.mean(axis=1)
        n_rows = len(target)
        n_clusters = min(5, n_rows)
        if n_clusters <= 1:
            cluster_ids = np.zeros(n_rows, dtype=int)
        else:
            rank = score.rank(method="first")
            cluster_ids = pd.qcut(rank, q=n_clusters, labels=False, duplicates="drop").astype(int).to_numpy()
        out = target[["country_code", "country", "year"]].copy()
        out["cluster_id"] = cluster_ids
        out["latest_valid_year"] = latest_valid_year
        outputs.append(out)

    if not outputs:
        return pd.DataFrame(columns=["country_code", "country", "year", "cluster_id", "latest_valid_year"])
    clusters = pd.concat(outputs, ignore_index=True)
    clusters = _collapse_duplicate_country_year_rows(clusters)
    clusters = clusters.sort_values(["country_code", "year"]).reset_index(drop=True)
    clusters = _add_runtime_metadata(clusters, metadata)
    return clusters


def _validate_analytics_table(
    *,
    table_name: str,
    table_df: pd.DataFrame,
    required_columns: list[str],
    expected_indicator_columns: list[str],
    enforce_unique_country_year: bool = True,
) -> dict[str, Any]:
    key_columns = ("country_code", "year") if enforce_unique_country_year else ("country_code", "year")
    summary = summarize_dataframe_validation(
        df=table_df,
        table_name=table_name,
        required_columns=required_columns,
        key_columns=key_columns,
    )
    if summary.row_count <= 0:
        raise ValueError(f"{table_name} is empty.")
    if summary.missing_columns:
        raise ValueError(f"{table_name} missing required columns: {summary.missing_columns}")
    if enforce_unique_country_year and summary.duplicate_key_count != 0:
        raise ValueError(f"{table_name} duplicate country/year keys: {summary.duplicate_key_count}")
    missing_indicator_columns = [column for column in expected_indicator_columns if column not in table_df.columns]
    if missing_indicator_columns:
        raise ValueError(
            f"{table_name} missing expected analytics columns: {missing_indicator_columns[:10]}"
        )
    if validate_country_code_iso3(table_df):
        raise ValueError(f"{table_name} contains invalid ISO3 country_code values.")
    if validate_year_range(table_df):
        raise ValueError(f"{table_name} contains invalid year values.")
    return {
        "table_name": table_name,
        "row_count": summary.row_count,
        "column_count": summary.column_count,
        "duplicate_key_count": summary.duplicate_key_count,
        "missing_columns": summary.missing_columns,
        "missing_indicator_columns": missing_indicator_columns,
    }


def build_analytics_tables(
    *,
    repo_root: Path,
    gold_tables: dict[str, pd.DataFrame],
    metadata: RuntimeMetadata,
    contract: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    indicator_contract = _load_indicator_contract_module(repo_root)
    tables_indicators: dict[str, list[str]] = dict(indicator_contract.TABLES_INDICATORS)
    public_indicators: dict[str, dict[str, Any]] = dict(indicator_contract.PUBLIC_INDICATORS)
    cluster_indicators: list[str] = list(indicator_contract.INDICATORS_FOR_CLUSTER)

    analytics_output = _ensure_dir(output_dir / "analytics")
    built_tables: dict[str, pd.DataFrame] = {}
    summaries: list[dict[str, Any]] = []

    for gold_table_name, indicators in tables_indicators.items():
        analytics_table_name = f"analytics_{gold_table_name}"
        gold_df = gold_tables[gold_table_name]
        built = _build_analytics_table_from_gold(
            gold_df=gold_df,
            indicators=indicators,
            metadata=metadata,
        )
        required_columns = get_table_contract_columns(contract, "analytics", analytics_table_name)
        if not required_columns:
            required_columns = ["country_code", "country", "year", "run_id", "run_date", "loaded_at"]
        expected_columns: list[str] = []
        for indicator in indicators:
            expected_columns.extend(
                [
                    f"{indicator}_actual",
                    f"{indicator}_trend",
                    f"{indicator}_residual",
                    f"{indicator}_slope",
                    f"{indicator}_intercept",
                    f"{indicator}_r2",
                    f"{indicator}_anomaly_score",
                ]
            )
        summary = _validate_analytics_table(
            table_name=analytics_table_name,
            table_df=built,
            required_columns=required_columns,
            expected_indicator_columns=expected_columns,
        )
        destination = _ensure_dir(analytics_output / analytics_table_name)
        built.to_parquet(destination / "part-00000.parquet", index=False)
        summary["parquet_path"] = str((destination / "part-00000.parquet").resolve())
        built_tables[analytics_table_name] = built
        summaries.append(summary)

    clusters = _build_clusters(
        gold_tables=gold_tables,
        cluster_indicators=cluster_indicators,
        public_indicators=public_indicators,
        metadata=metadata,
    )
    required_cluster_columns = get_table_contract_columns(contract, "analytics", "analytics_clusters")
    if not required_cluster_columns:
        required_cluster_columns = [
            "country_code",
            "country",
            "year",
            "cluster_id",
            "latest_valid_year",
            "run_id",
            "run_date",
            "loaded_at",
        ]
    cluster_summary = _validate_analytics_table(
        table_name="analytics_clusters",
        table_df=clusters,
        required_columns=required_cluster_columns,
        expected_indicator_columns=["cluster_id", "latest_valid_year"],
    )
    cluster_destination = _ensure_dir(analytics_output / "analytics_clusters")
    clusters.to_parquet(cluster_destination / "part-00000.parquet", index=False)
    cluster_summary["parquet_path"] = str((cluster_destination / "part-00000.parquet").resolve())
    summaries.append(cluster_summary)
    built_tables["analytics_clusters"] = clusters

    return built_tables, summaries


def build_publish_plan(
    *,
    metadata: RuntimeMetadata,
    gold_tables: dict[str, pd.DataFrame],
    analytics_tables: dict[str, pd.DataFrame],
    project_id: str,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    plan_tables: list[dict[str, Any]] = []
    for table_name in GOLD_TABLE_NAMES:
        plan_tables.append(
            {
                "dataset": "gov_ai_gold",
                "staging_table": f"{table_name}_staging_run_{timestamp}",
                "production_table": table_name,
                "production_table_id": f"{project_id}.gov_ai_gold.{table_name}",
                "row_count": int(len(gold_tables[table_name])),
            }
        )
    for table_name in ANALYTICS_TABLE_NAMES:
        plan_tables.append(
            {
                "dataset": "gov_ai_analytics",
                "staging_table": f"{table_name}_staging_run_{timestamp}",
                "production_table": table_name,
                "production_table_id": f"{project_id}.gov_ai_analytics.{table_name}",
                "row_count": int(len(analytics_tables[table_name])),
            }
        )
    return {
        "write_strategy": "staging_validate_write_truncate",
        "tables": plan_tables,
    }


def run_warehouse_rebuild(
    *,
    project_id: str,
    location: str,
    silver_table_id: str = DEFAULT_SILVER_TABLE,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    expected_silver_row_count: int | None = None,
    max_validation_bytes: int = DEFAULT_MAX_VALIDATION_BYTES,
) -> dict[str, Any]:
    repo_root = _resolve_repo_root()
    output_path = _ensure_dir(Path(output_dir).expanduser().resolve())
    require_active_project(project_id)
    executor = BigQueryExecutor(project_id=project_id, location=location)

    preflight = run_silver_preflight(
        executor=executor,
        silver_table_id=silver_table_id,
        expected_row_count=expected_silver_row_count,
        required_columns=REQUIRED_SILVER_COLUMNS,
        non_null_columns=REQUIRED_SILVER_NON_NULL_COLUMNS,
        max_validation_bytes=max_validation_bytes,
    )
    _json_dump(output_path / "silver_preflight.json", preflight)

    silver_df = fetch_silver_dataframe(
        executor=executor,
        silver_table_id=silver_table_id,
        output_dir=output_path,
        max_bytes_billed=max_validation_bytes,
    )
    metadata = derive_runtime_metadata(silver_df)

    contract = load_table_contract(repo_root / "contracts" / "table_contract.yaml")
    gold_tables, gold_summary = build_gold_tables(
        silver_df=silver_df,
        metadata=metadata,
        contract=contract,
        output_dir=output_path,
    )
    analytics_tables, analytics_summary = build_analytics_tables(
        repo_root=repo_root,
        gold_tables=gold_tables,
        metadata=metadata,
        contract=contract,
        output_dir=output_path,
    )
    publish_plan = build_publish_plan(
        metadata=metadata,
        gold_tables=gold_tables,
        analytics_tables=analytics_tables,
        project_id=project_id,
    )
    _json_dump(output_path / "publish_plan.json", publish_plan)

    result = {
        "project_id": project_id,
        "location": location,
        "silver_table_id": silver_table_id,
        "output_dir": str(output_path),
        "bigquery_backend": executor.backend,
        "metadata": {
            "run_id": metadata.run_id,
            "run_date": str(metadata.run_date),
            "loaded_at": metadata.loaded_at.isoformat(),
        },
        "silver_preflight": preflight,
        "gold_summary": gold_summary,
        "analytics_summary": analytics_summary,
        "publish_plan": publish_plan,
    }
    _json_dump(output_path / "rebuild_summary.json", result)
    return result
