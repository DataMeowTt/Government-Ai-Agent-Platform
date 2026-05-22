from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: PyYAML. Install with: pip install pyyaml"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]

CONTRACTS_DIR = ROOT / "contracts"
REPORTS_DIR = ROOT / "reports"

INDICATOR_CONTRACT_PATH = CONTRACTS_DIR / "indicator_contract.yaml"
TABLE_CONTRACT_PATH = CONTRACTS_DIR / "table_contract.yaml"
DATA_QUALITY_RULES_PATH = CONTRACTS_DIR / "data_quality_rules.yaml"

DATA_QUALITY_REPORT_PATH = REPORTS_DIR / "data_quality_report.json"
INDICATOR_MISMATCH_REPORT_PATH = REPORTS_DIR / "indicator_mismatch_report.json"

GOLD_TABLES = (
    "gold_growth_dynamics",
    "gold_fiscal_monetary",
    "gold_crisis_risk",
    "gold_social_welfare",
    "gold_structural_composition",
)

ANALYTICS_TIME_SERIES_TABLES = (
    "analytics_gold_growth_dynamics",
    "analytics_gold_fiscal_monetary",
    "analytics_gold_crisis_risk",
    "analytics_gold_social_welfare",
    "analytics_gold_structural_composition",
)

ANALYTICS_CLUSTER_TABLE = "analytics_clusters"

EXPECTED_TREND_SUFFIXES = (
    "_actual",
    "_trend",
    "_residual",
    "_slope",
    "_intercept",
    "_r2",
)

EXPECTED_ANOMALY_SUFFIXES = (
    "_anomaly_score",
)

EXPECTED_ANALYTICS_SUFFIXES = EXPECTED_TREND_SUFFIXES + EXPECTED_ANOMALY_SUFFIXES

METADATA_KEYS = {
    "version",
    "schema_version",
    "contract_version",
    "metadata",
    "description",
    "notes",
    "defaults",
    "generated_at",
    "analytics",
    "clusters",
    "tables",
    "warehouse",
    "datasets",
}


@dataclass
class AuditState:
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    info: list[dict[str, Any]] = field(default_factory=list)

    mismatch_report: dict[str, Any] = field(
        default_factory=lambda: {
            "status": "passed",
            "missing_in_silver": [],
            "missing_in_gold": [],
            "unknown_silver_indicators": [],
            "unknown_gold_public_columns": [],
            "analytics_missing_columns": [],
            "cluster_mismatches": [],
        }
    )

    def add_check(
        self,
        name: str,
        status: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.checks.append(
            {
                "name": name,
                "status": status,
                "severity": severity,
                "message": message,
                "details": details or {},
            }
        )

    def add_error(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        item = {
            "check": check_name,
            "message": message,
            "details": details or {},
        }
        self.errors.append(item)
        self.add_check(check_name, "failed", "error", message, details)

    def add_warning(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        item = {
            "check": check_name,
            "message": message,
            "details": details or {},
        }
        self.warnings.append(item)
        self.add_check(check_name, "warning", "warning", message, details)

    def add_info(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        item = {
            "check": check_name,
            "message": message,
            "details": details or {},
        }
        self.info.append(item)
        self.add_check(check_name, "passed", "info", message, details)

    def add_skipped(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.add_check(check_name, "skipped", "info", message, details)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path.relative_to(ROOT)}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path.relative_to(ROOT)}")

    return data


def write_json(path: Path, payload: dict[str, Any], indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_repo_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path

    return ROOT / path


def format_path_for_report(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def audit_optional_runtime_path(
    state: AuditState,
    check_name: str,
    label: str,
    path: Path | None,
    expected_kind: str,
) -> None:
    if path is None:
        state.add_skipped(
            check_name,
            f"{label} runtime path was not provided.",
            {
                "expected_kind": expected_kind,
                "next_step": "Pass the path via CLI when concrete pipeline output exists.",
            },
        )
        return

    if not path.exists():
        state.add_error(
            check_name,
            f"{label} runtime path does not exist.",
            {
                "path": format_path_for_report(path),
                "expected_kind": expected_kind,
            },
        )
        return

    if expected_kind == "file" and not path.is_file():
        state.add_error(
            check_name,
            f"{label} runtime path must be a file.",
            {
                "path": format_path_for_report(path),
                "expected_kind": expected_kind,
                "actual_is_dir": path.is_dir(),
            },
        )
        return

    if expected_kind == "directory" and not path.is_dir():
        state.add_error(
            check_name,
            f"{label} runtime path must be a directory.",
            {
                "path": format_path_for_report(path),
                "expected_kind": expected_kind,
                "actual_is_file": path.is_file(),
            },
        )
        return

    state.add_info(
        check_name,
        f"{label} runtime path exists.",
        {
            "path": format_path_for_report(path),
            "expected_kind": expected_kind,
        },
    )


def audit_runtime_data_paths(
    state: AuditState,
    silver_path: Path | None,
    gold_dir: Path | None,
    analytics_dir: Path | None,
) -> None:
    audit_optional_runtime_path(
        state,
        "silver_runtime_path_available",
        "Silver",
        silver_path,
        "path",
    )
    audit_optional_runtime_path(
        state,
        "gold_runtime_path_available",
        "Gold",
        gold_dir,
        "directory",
    )
    audit_optional_runtime_path(
        state,
        "analytics_runtime_path_available",
        "Analytics",
        analytics_dir,
        "directory",
    )

def normalize_indicator_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)

    for key in (
        "public",
        "technical",
        "dimension",
        "supports_raw",
        "supports_compare",
        "supports_ranking",
        "supports_coverage",
        "supports_trend",
        "supports_anomaly",
        "used_for_cluster",
    ):
        normalized[key] = bool(normalized.get(key, False))

    normalized["source_priority"] = list(normalized.get("source_priority") or [])
    normalized["aliases_vi"] = list(normalized.get("aliases_vi") or [])
    normalized["aliases_en"] = list(normalized.get("aliases_en") or [])
    normalized["additional_gold_locations"] = list(
        normalized.get("additional_gold_locations") or []
    )
    normalized["applies_to_gold_tables"] = list(
        normalized.get("applies_to_gold_tables") or []
    )

    return normalized


def extract_indicator_entries(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if isinstance(raw.get("indicators"), dict):
        candidates = raw["indicators"]
    elif isinstance(raw.get("entries"), dict):
        candidates = raw["entries"]
    else:
        candidates = {
            key: value
            for key, value in raw.items()
            if key not in METADATA_KEYS and isinstance(value, dict)
        }

    indicators: dict[str, dict[str, Any]] = {}

    for key, value in candidates.items():
        if not isinstance(value, dict):
            continue

        code = str(value.get("code") or key).strip()
        if not code:
            raise ValueError(f"Indicator entry has empty code: {key}")

        entry = dict(value)
        entry["code"] = code
        indicators[code] = normalize_indicator_entry(entry)

    if not indicators:
        raise ValueError("No indicator entries found in indicator_contract.yaml")

    return indicators


def is_public_indicator(entry: dict[str, Any]) -> bool:
    return (
        bool(entry.get("public"))
        and not bool(entry.get("technical"))
        and not bool(entry.get("dimension"))
    )


def get_public_indicators(
    indicators: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        code: entry
        for code, entry in indicators.items()
        if is_public_indicator(entry)
    }


def get_technical_entries(
    indicators: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        code: entry
        for code, entry in indicators.items()
        if bool(entry.get("technical"))
    }


def get_section_table_spec(
    table_contract: dict[str, Any],
    section_name: str,
    table_name: str,
) -> dict[str, Any]:
    section = table_contract.get(section_name)
    if not isinstance(section, dict):
        return {}

    spec = section.get(table_name)
    return spec if isinstance(spec, dict) else {}


def get_table_spec(table_contract: dict[str, Any], table_name: str) -> dict[str, Any]:
    for section_name in ("silver", "gold", "analytics", "ops"):
        spec = get_section_table_spec(table_contract, section_name, table_name)
        if spec:
            return spec
    return {}


def get_table_columns(table_spec: dict[str, Any]) -> set[str]:
    columns = table_spec.get("columns")
    if isinstance(columns, dict):
        return {str(column) for column in columns.keys()}

    required_columns = table_spec.get("required_columns")
    if isinstance(required_columns, list):
        return {str(column) for column in required_columns}

    return set()


def get_table_grain(table_spec: dict[str, Any]) -> list[str]:
    grain = table_spec.get("grain")
    if isinstance(grain, list):
        return [str(column) for column in grain]
    return []


def get_rule_columns(
    rules: dict[str, Any],
    section_name: str,
    rule_name: str,
    key: str = "columns",
) -> list[str]:
    section = rules.get(section_name)
    if not isinstance(section, dict):
        return []

    rule = section.get(rule_name)
    if not isinstance(rule, dict):
        return []

    values = rule.get(key)
    if isinstance(values, list):
        return [str(value) for value in values]

    return []


def get_rule_key(
    rules: dict[str, Any],
    section_name: str,
    rule_name: str,
) -> list[str]:
    return get_rule_columns(rules, section_name, rule_name, key="key")


def dataset_for_table(table_contract: dict[str, Any], table_name: str) -> str | None:
    spec = get_table_spec(table_contract, table_name)
    dataset = spec.get("dataset")
    return str(dataset) if dataset else None


def analytics_table_for_gold_table(gold_table: str) -> str:
    return f"analytics_{gold_table}"


def build_gold_expected_public_columns(
    public_indicators: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    for code, entry in public_indicators.items():
        gold_table = entry.get("gold_table")
        gold_column = entry.get("gold_column") or code

        if gold_table and gold_column:
            result.setdefault(str(gold_table), set()).add(str(gold_column))

        for location in entry.get("additional_gold_locations") or []:
            if not isinstance(location, dict):
                continue

            extra_table = location.get("gold_table")
            extra_column = location.get("gold_column")

            if extra_table and extra_column:
                result.setdefault(str(extra_table), set()).add(str(extra_column))

    return result


def build_analytics_expected_columns(
    public_indicators: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    for code, entry in public_indicators.items():
        if not (entry.get("supports_trend") or entry.get("supports_anomaly")):
            continue

        gold_table = entry.get("gold_table")
        if not gold_table:
            continue

        analytics_table = analytics_table_for_gold_table(str(gold_table))
        result.setdefault(analytics_table, set()).add(f"{code}_actual")

        if entry.get("supports_trend"):
            for suffix in EXPECTED_TREND_SUFFIXES:
                result[analytics_table].add(f"{code}{suffix}")

        if entry.get("supports_anomaly"):
            for suffix in EXPECTED_ANOMALY_SUFFIXES:
                result[analytics_table].add(f"{code}{suffix}")

    return result


def audit_required_files(state: AuditState) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}

    for name, path in (
        ("indicator_contract", INDICATOR_CONTRACT_PATH),
        ("table_contract", TABLE_CONTRACT_PATH),
        ("data_quality_rules", DATA_QUALITY_RULES_PATH),
    ):
        try:
            loaded[name] = load_yaml(path)
            state.add_info(
                "required_file_exists",
                f"Loaded {path.relative_to(ROOT)}",
                {"file": str(path.relative_to(ROOT))},
            )
        except Exception as exc:
            state.add_error(
                "required_file_exists",
                f"Cannot load {path.relative_to(ROOT)}: {exc}",
                {"file": str(path.relative_to(ROOT))},
            )
            loaded[name] = {}

    return (
        loaded["indicator_contract"],
        loaded["table_contract"],
        loaded["data_quality_rules"],
    )


def audit_rules_defaults(state: AuditState, rules: dict[str, Any]) -> None:
    defaults = rules.get("defaults") if isinstance(rules.get("defaults"), dict) else {}

    min_year = defaults.get("min_year")
    max_year = defaults.get("max_year")
    allowed_sources = defaults.get("allowed_sources") or []
    country_code_regex = defaults.get("country_code_regex")

    if min_year != 1980 or max_year != 2030:
        state.add_warning(
            "rules_defaults_year_range",
            "data_quality_rules.yaml year range differs from expected 1980-2030.",
            {"min_year": min_year, "max_year": max_year},
        )
    else:
        state.add_info(
            "rules_defaults_year_range",
            "Default year range is 1980-2030.",
            {"min_year": min_year, "max_year": max_year},
        )

    if list(allowed_sources) != ["wdi", "gmd", "macro"]:
        state.add_warning(
            "rules_defaults_allowed_sources",
            "Allowed sources differ from expected ['wdi', 'gmd', 'macro'].",
            {"allowed_sources": allowed_sources},
        )
    else:
        state.add_info(
            "rules_defaults_allowed_sources",
            "Allowed sources are wdi/gmd/macro.",
            {"allowed_sources": allowed_sources},
        )

    if country_code_regex != "^[A-Z]{3}$":
        state.add_warning(
            "rules_defaults_country_code_regex",
            "country_code_regex differs from expected ISO3 regex.",
            {"country_code_regex": country_code_regex},
        )
    else:
        state.add_info(
            "rules_defaults_country_code_regex",
            "country_code_regex uses ISO3 format.",
            {"country_code_regex": country_code_regex},
        )


def extract_declared_datasets(table_contract: dict[str, Any]) -> set[str]:
    datasets: set[str] = set()

    raw_datasets = table_contract.get("datasets")

    if isinstance(raw_datasets, dict):
        datasets.update(str(key) for key in raw_datasets.keys())
    elif isinstance(raw_datasets, list):
        for item in raw_datasets:
            if isinstance(item, str):
                datasets.add(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("dataset")
                if name:
                    datasets.add(str(name))

    for section_name in ("silver", "gold", "analytics", "ops"):
        section = table_contract.get(section_name)
        if not isinstance(section, dict):
            continue

        for table_spec in section.values():
            if isinstance(table_spec, dict) and table_spec.get("dataset"):
                datasets.add(str(table_spec["dataset"]))

    return datasets


def extract_declared_table_names(table_contract: dict[str, Any]) -> set[str]:
    table_names: set[str] = set()

    for section_name in ("silver", "gold", "analytics", "ops"):
        section = table_contract.get(section_name)
        if isinstance(section, dict):
            table_names.update(str(table_name) for table_name in section.keys())

    return table_names


def get_nested_rule_list(
    rules: dict[str, Any],
    section_name: str,
    rule_name: str,
    field_name: str,
) -> list[str]:
    section = rules.get(section_name)
    if not isinstance(section, dict):
        return []

    rule = section.get(rule_name)
    if not isinstance(rule, dict):
        return []

    values = rule.get(field_name)
    if not isinstance(values, list):
        return []

    return [str(value) for value in values]


def audit_contract_rules_consistency_static(
    state: AuditState,
    indicators: dict[str, dict[str, Any]],
    table_contract: dict[str, Any],
    rules: dict[str, Any],
) -> None:
    public_indicators = get_public_indicators(indicators)
    technical_entries = get_technical_entries(indicators)

    declared_table_names = extract_declared_table_names(table_contract)
    declared_datasets = extract_declared_datasets(table_contract)

    required_bigquery_datasets = set(
        get_nested_rule_list(
            rules,
            "bigquery_rules",
            "datasets_must_exist",
            "datasets",
        )
    )

    if required_bigquery_datasets:
        missing_datasets = sorted(required_bigquery_datasets - declared_datasets)

        if missing_datasets:
            state.add_error(
                "contract_rules_bigquery_datasets_static",
                "BigQuery datasets required by data_quality_rules.yaml are missing from table_contract.yaml.",
                {
                    "missing_datasets": missing_datasets,
                    "required_datasets": sorted(required_bigquery_datasets),
                    "declared_datasets": sorted(declared_datasets),
                },
            )
        else:
            state.add_info(
                "contract_rules_bigquery_datasets_static",
                "BigQuery datasets in data_quality_rules.yaml are declared in table_contract.yaml.",
                {
                    "required_datasets": sorted(required_bigquery_datasets),
                    "declared_datasets": sorted(declared_datasets),
                },
            )
    else:
        state.add_warning(
            "contract_rules_bigquery_datasets_static",
            "No datasets_must_exist rule found under bigquery_rules.",
        )

    synced_tables = set(
        get_nested_rule_list(
            rules,
            "postgres_sync_rules",
            "synced_tables",
            "tables",
        )
    )

    if synced_tables:
        missing_synced_tables = sorted(synced_tables - declared_table_names)

        if missing_synced_tables:
            state.add_error(
                "contract_rules_postgres_synced_tables_static",
                "postgres_sync_rules references tables missing from table_contract.yaml.",
                {
                    "missing_tables": missing_synced_tables,
                    "synced_tables": sorted(synced_tables),
                },
            )
        else:
            state.add_info(
                "contract_rules_postgres_synced_tables_static",
                "All postgres_sync_rules synced tables exist in table_contract.yaml.",
                {"synced_tables": sorted(synced_tables)},
            )
    else:
        state.add_warning(
            "contract_rules_postgres_synced_tables_static",
            "No postgres_sync_rules.synced_tables rule found.",
        )

    public_gold_tables = {
        str(entry.get("gold_table"))
        for entry in public_indicators.values()
        if entry.get("gold_table")
    }

    missing_public_gold_tables = sorted(public_gold_tables - declared_table_names)

    if missing_public_gold_tables:
        state.add_error(
            "contract_rules_public_indicator_gold_tables_static",
            "Some public indicators reference gold_table values missing from table_contract.yaml.",
            {
                "missing_gold_tables": missing_public_gold_tables,
                "public_gold_tables": sorted(public_gold_tables),
            },
        )
    else:
        state.add_info(
            "contract_rules_public_indicator_gold_tables_static",
            "All public indicator gold_table values exist in table_contract.yaml.",
            {"public_gold_tables": sorted(public_gold_tables)},
        )

    rule_technical_columns = set(
        get_rule_columns(
            rules,
            "gold_rules",
            "technical_columns_not_public",
            key="technical_columns",
        )
    )

    missing_technical_entries = sorted(rule_technical_columns - set(technical_entries.keys()))

    if missing_technical_entries:
        state.add_error(
            "contract_rules_technical_columns_static",
            "Technical columns in data_quality_rules.yaml are missing as technical entries in indicator_contract.yaml.",
            {
                "missing_technical_entries": missing_technical_entries,
                "rule_technical_columns": sorted(rule_technical_columns),
            },
        )
    else:
        state.add_info(
            "contract_rules_technical_columns_static",
            "Technical columns in data_quality_rules.yaml are aligned with indicator_contract.yaml.",
            {
                "rule_technical_columns": sorted(rule_technical_columns),
                "technical_entries": sorted(technical_entries.keys()),
            },
        )

    non_technical_rule_entries = sorted(
        code
        for code in rule_technical_columns
        if code in indicators and not indicators[code].get("technical")
    )

    if non_technical_rule_entries:
        state.add_error(
            "contract_rules_technical_columns_not_public_static",
            "Some rule technical columns are not marked technical=true in indicator_contract.yaml.",
            {"indicators": non_technical_rule_entries},
        )
    else:
        state.add_info(
            "contract_rules_technical_columns_not_public_static",
            "Rule technical columns are marked technical=true when present in indicator_contract.yaml.",
            {"checked_columns": sorted(rule_technical_columns)},
        )

    no_interpolate_rule_indicators = set(
        get_rule_columns(
            rules,
            "gold_rules",
            "preserve_null_for_no_interpolate_indicators",
            key="indicators",
        )
    )

    missing_no_interpolate_entries = sorted(
        no_interpolate_rule_indicators - set(indicators.keys())
    )

    if missing_no_interpolate_entries:
        state.add_error(
            "contract_rules_no_interpolate_entries_static",
            "No-interpolate indicators in data_quality_rules.yaml are missing from indicator_contract.yaml.",
            {"missing_indicators": missing_no_interpolate_entries},
        )
    else:
        state.add_info(
            "contract_rules_no_interpolate_entries_static",
            "No-interpolate indicators in data_quality_rules.yaml exist in indicator_contract.yaml.",
            {"indicators": sorted(no_interpolate_rule_indicators)},
        )

    cluster_spec = get_section_table_spec(
        table_contract,
        "analytics",
        ANALYTICS_CLUSTER_TABLE,
    )
    cluster_required_columns = set(get_table_columns(cluster_spec))

    if not cluster_required_columns:
        required_columns = cluster_spec.get("required_columns") if cluster_spec else []
        if isinstance(required_columns, list):
            cluster_required_columns = {str(column) for column in required_columns}

    expected_cluster_columns = {
        "country_code",
        "country",
        "year",
        "cluster_id",
        "latest_valid_year",
    }

    missing_cluster_columns = sorted(expected_cluster_columns - cluster_required_columns)

    if missing_cluster_columns:
        for column in missing_cluster_columns:
            item = {
                "table": ANALYTICS_CLUSTER_TABLE,
                "column": column,
                "source": "contract_rules_consistency",
            }
            state.mismatch_report["analytics_missing_columns"].append(item)
            state.mismatch_report["cluster_mismatches"].append(item)

        state.add_error(
            "contract_rules_cluster_required_columns_static",
            "analytics_clusters is missing required business/key columns in table_contract.yaml.",
            {
                "missing_columns": missing_cluster_columns,
                "expected_columns": sorted(expected_cluster_columns),
            },
        )
    else:
        state.add_info(
            "contract_rules_cluster_required_columns_static",
            "analytics_clusters declares required key/business columns.",
            {"required_columns": sorted(expected_cluster_columns)},
        )

    latest_valid_year_rule_columns = set(
        get_rule_columns(
            rules,
            "analytics_rules",
            "cluster_latest_valid_year_required",
            key="required_columns",
        )
    )

    if "latest_valid_year" not in latest_valid_year_rule_columns:
        item = {
            "table": ANALYTICS_CLUSTER_TABLE,
            "column": "latest_valid_year",
            "rule": "cluster_latest_valid_year_required",
        }
        state.mismatch_report["cluster_mismatches"].append(item)
        state.add_error(
            "contract_rules_cluster_latest_valid_year_static",
            "data_quality_rules.yaml must require latest_valid_year for analytics_clusters.",
            item,
        )
    else:
        state.add_info(
            "contract_rules_cluster_latest_valid_year_static",
            "data_quality_rules.yaml requires latest_valid_year for analytics_clusters.",
            {"required_columns": sorted(latest_valid_year_rule_columns)},
        )

    trend_suffixes = tuple(
        get_rule_columns(
            rules,
            "analytics_rules",
            "trend_columns_required_for_supported_indicators",
            key="required_suffixes",
        )
    )
    anomaly_suffixes = tuple(
        get_rule_columns(
            rules,
            "analytics_rules",
            "anomaly_columns_required_for_supported_indicators",
            key="required_suffixes",
        )
    )

    if trend_suffixes != EXPECTED_TREND_SUFFIXES:
        state.add_error(
            "contract_rules_trend_suffixes_static",
            "Trend suffixes in data_quality_rules.yaml drifted from expected contract suffixes.",
            {
                "actual": list(trend_suffixes),
                "expected": list(EXPECTED_TREND_SUFFIXES),
            },
        )
    else:
        state.add_info(
            "contract_rules_trend_suffixes_static",
            "Trend suffixes in data_quality_rules.yaml match expected contract suffixes.",
            {"suffixes": list(trend_suffixes)},
        )

    if anomaly_suffixes != EXPECTED_ANOMALY_SUFFIXES:
        state.add_error(
            "contract_rules_anomaly_suffixes_static",
            "Anomaly suffixes in data_quality_rules.yaml drifted from expected contract suffixes.",
            {
                "actual": list(anomaly_suffixes),
                "expected": list(EXPECTED_ANOMALY_SUFFIXES),
            },
        )
    else:
        state.add_info(
            "contract_rules_anomaly_suffixes_static",
            "Anomaly suffixes in data_quality_rules.yaml match expected contract suffixes.",
            {"suffixes": list(anomaly_suffixes)},
        )

def audit_indicator_contract_shape(
    state: AuditState,
    indicators: dict[str, dict[str, Any]],
) -> None:
    public_indicators = get_public_indicators(indicators)
    technical_entries = get_technical_entries(indicators)

    if not public_indicators:
        state.add_error(
            "indicator_contract_public_entries",
            "No public indicators found.",
        )
    else:
        state.add_info(
            "indicator_contract_public_entries",
            "Public indicators loaded.",
            {"count": len(public_indicators)},
        )

    for code, entry in sorted(public_indicators.items()):
        missing_fields = [
            field_name
            for field_name in ("gold_table", "gold_column", "source_indicator")
            if not entry.get(field_name)
        ]

        if missing_fields:
            state.add_error(
                "public_indicator_required_fields",
                f"Public indicator {code} is missing required fields.",
                {"indicator": code, "missing_fields": missing_fields},
            )

    for code, entry in sorted(technical_entries.items()):
        if entry.get("public"):
            state.add_error(
                "technical_columns_not_public",
                f"Technical entry {code} must not be public.",
                {"indicator": code},
            )

    if technical_entries:
        state.add_info(
            "technical_entries_loaded",
            "Technical entries loaded.",
            {"technical_entries": sorted(technical_entries.keys())},
        )


def audit_no_interpolate_policy(
    state: AuditState,
    indicators: dict[str, dict[str, Any]],
    rules: dict[str, Any],
) -> None:
    rule_indicators = get_rule_columns(
        rules,
        "gold_rules",
        "preserve_null_for_no_interpolate_indicators",
        key="indicators",
    )

    if not rule_indicators:
        state.add_warning(
            "no_interpolate_rule_present",
            "No preserve_null_for_no_interpolate_indicators rule found.",
        )
        return

    for code in rule_indicators:
        entry = indicators.get(code)

        if not entry:
            state.add_error(
                "no_interpolate_indicator_exists",
                f"{code} is listed in no_interpolate rules but missing in indicator_contract.yaml.",
                {"indicator": code},
            )
            continue

        imputation_policy = entry.get("imputation_policy")
        null_policy = entry.get("null_policy")

        if imputation_policy != "no_interpolate":
            state.add_error(
                "no_interpolate_policy_alignment",
                f"{code} must use imputation_policy=no_interpolate.",
                {
                    "indicator": code,
                    "actual_imputation_policy": imputation_policy,
                    "expected_imputation_policy": "no_interpolate",
                },
            )

        if null_policy != "preserve_null":
            state.add_warning(
                "no_interpolate_null_policy_alignment",
                f"{code} should use null_policy=preserve_null.",
                {
                    "indicator": code,
                    "actual_null_policy": null_policy,
                    "expected_null_policy": "preserve_null",
                },
            )

    state.add_info(
        "no_interpolate_rule_present",
        "Checked no_interpolate indicators from data_quality_rules.yaml.",
        {"indicators": rule_indicators},
    )


def audit_silver_contract_static(
    state: AuditState,
    table_contract: dict[str, Any],
    rules: dict[str, Any],
) -> None:
    silver_spec = get_section_table_spec(table_contract, "silver", "silver_indicators")
    silver_columns = get_table_columns(silver_spec)

    required_columns = get_rule_columns(
        rules,
        "silver_rules",
        "required_columns",
        key="columns",
    )

    missing_required = sorted(set(required_columns) - silver_columns)

    if missing_required:
        state.add_error(
            "silver_required_columns_static",
            "silver_indicators is missing required columns in table_contract.yaml.",
            {"missing_columns": missing_required},
        )
    else:
        state.add_info(
            "silver_required_columns_static",
            "silver_indicators has required columns in table_contract.yaml.",
            {"required_columns": required_columns},
        )

    expected_key = get_rule_key(
        rules,
        "silver_rules",
        "no_duplicate_country_year_indicator_source",
    )
    actual_grain = get_table_grain(silver_spec)

    if expected_key and actual_grain and expected_key != actual_grain:
        state.add_warning(
            "silver_grain_vs_duplicate_key_static",
            "silver_indicators grain differs from duplicate key rule.",
            {"rule_key": expected_key, "table_grain": actual_grain},
        )
    else:
        state.add_info(
            "silver_grain_vs_duplicate_key_static",
            "silver_indicators grain matches duplicate key rule.",
            {"rule_key": expected_key, "table_grain": actual_grain},
        )

    state.add_skipped(
        "silver_dataset_content_checks",
        (
            "Silver data content checks are deferred until a concrete Silver "
            "CSV/Parquet path is wired into the audit script."
        ),
        {
            "deferred_checks": [
                "unknown_silver_indicators",
                "missing_in_silver",
                "source_coverage",
                "null_rate_by_indicator_source",
            ]
        },
    )


def audit_gold_contract_static(
    state: AuditState,
    indicators: dict[str, dict[str, Any]],
    table_contract: dict[str, Any],
    rules: dict[str, Any],
) -> None:
    public_indicators = get_public_indicators(indicators)
    technical_entries = get_technical_entries(indicators)

    expected_public_columns_by_table = build_gold_expected_public_columns(public_indicators)

    required_key_columns = set(
        get_rule_columns(
            rules,
            "gold_rules",
            "required_key_columns",
            key="columns",
        )
    )
    allowed_columns = set(
        get_rule_columns(
            rules,
            "gold_rules",
            "no_unknown_public_gold_column",
            key="allow_columns",
        )
    )
    technical_columns = set(
        get_rule_columns(
            rules,
            "gold_rules",
            "technical_columns_not_public",
            key="technical_columns",
        )
    )
    technical_columns.update(technical_entries.keys())

    for table_name in GOLD_TABLES:
        table_spec = get_section_table_spec(table_contract, "gold", table_name)
        table_columns = get_table_columns(table_spec)

        if not table_spec:
            state.add_error(
                "gold_table_contract_exists",
                f"{table_name} is missing in table_contract.yaml.",
                {"table": table_name},
            )
            continue

        missing_key_columns = sorted(required_key_columns - table_columns)
        if missing_key_columns:
            state.add_error(
                "gold_required_key_columns_static",
                f"{table_name} is missing required key columns.",
                {"table": table_name, "missing_columns": missing_key_columns},
            )
        else:
            state.add_info(
                "gold_required_key_columns_static",
                f"{table_name} has required key columns.",
                {"table": table_name, "required_columns": sorted(required_key_columns)},
            )

        expected_public_columns = expected_public_columns_by_table.get(table_name, set())
        missing_public_columns = sorted(expected_public_columns - table_columns)

        for missing_column in missing_public_columns:
            indicators_for_column = [
                code
                for code, entry in public_indicators.items()
                if (
                    entry.get("gold_table") == table_name
                    and (entry.get("gold_column") or code) == missing_column
                )
                or any(
                    isinstance(location, dict)
                    and location.get("gold_table") == table_name
                    and location.get("gold_column") == missing_column
                    for location in entry.get("additional_gold_locations") or []
                )
            ]

            item = {
                "table": table_name,
                "column": missing_column,
                "indicators": sorted(indicators_for_column),
            }
            state.mismatch_report["missing_in_gold"].append(item)
            state.add_error(
                "gold_public_indicator_missing_static",
                f"{table_name} is missing expected public indicator column {missing_column}.",
                item,
            )

        allowed_non_public_columns = (
            allowed_columns
            | required_key_columns
            | technical_columns
            | {"country", "income_group", "development_group"}
        )

        unknown_public_columns = sorted(
            column
            for column in table_columns
            if column not in expected_public_columns
            and column not in allowed_non_public_columns
        )

        for column in unknown_public_columns:
            item = {
                "table": table_name,
                "column": column,
            }
            state.mismatch_report["unknown_gold_public_columns"].append(item)
            state.add_error(
                "gold_unknown_public_column_static",
                f"{table_name} has unknown public column {column}.",
                item,
            )

        for technical_column in sorted(technical_columns & table_columns):
            state.add_info(
                "gold_technical_column_present_static",
                f"{table_name} contains technical column {technical_column}; it must remain non-public.",
                {"table": table_name, "column": technical_column},
            )

    crisis_flag_columns = get_rule_columns(
        rules,
        "gold_rules",
        "crisis_binary_flags",
        key="columns",
    )
    crisis_allowed_values = get_rule_columns(
        rules,
        "gold_rules",
        "crisis_binary_flags",
        key="allowed_values",
    )

    if crisis_flag_columns and set(map(str, crisis_allowed_values)) == {"0", "1"}:
        state.add_info(
            "gold_crisis_binary_rule_static",
            (
                "Crisis binary rule exists. Runtime value audit must check only "
                "non-null values and must preserve null policy."
            ),
            {
                "columns": crisis_flag_columns,
                "allowed_non_null_values": [0, 1],
            },
        )
    else:
        state.add_warning(
            "gold_crisis_binary_rule_static",
            "Crisis binary rule is missing or not 0/1.",
            {
                "columns": crisis_flag_columns,
                "allowed_values": crisis_allowed_values,
            },
        )

    composite_allowed_values = get_rule_columns(
        rules,
        "gold_rules",
        "crisis_composite_range",
        key="allowed_values",
    )

    if set(map(str, composite_allowed_values)) == {"0", "1", "2", "3"}:
        state.add_info(
            "gold_crisis_composite_rule_static",
            (
                "crisis_composite rule exists. Runtime value audit must check only "
                "non-null values and must preserve null policy."
            ),
            {"allowed_non_null_values": [0, 1, 2, 3]},
        )
    else:
        state.add_warning(
            "gold_crisis_composite_rule_static",
            "crisis_composite rule is missing or not 0/1/2/3.",
            {"allowed_values": composite_allowed_values},
        )

    state.add_skipped(
        "gold_dataset_content_checks",
        (
            "Gold data content checks are deferred until concrete Gold table "
            "CSV/Parquet/PostgreSQL paths are wired into the audit script."
        ),
        {
            "deferred_checks": [
                "duplicate country_code/year rows",
                "country_code regex on data",
                "year range on data",
                "null rate per indicator",
                "suspicious zero count",
                "non-null crisis allowed values",
                "preserve null/no_interpolate runtime behavior",
            ]
        },
    )


def audit_analytics_contract_static(
    state: AuditState,
    indicators: dict[str, dict[str, Any]],
    table_contract: dict[str, Any],
    rules: dict[str, Any],
) -> None:
    public_indicators = get_public_indicators(indicators)
    expected_columns_by_table = build_analytics_expected_columns(public_indicators)

    rule_trend_suffixes = get_rule_columns(
        rules,
        "analytics_rules",
        "trend_columns_required_for_supported_indicators",
        key="required_suffixes",
    )
    rule_anomaly_suffixes = get_rule_columns(
        rules,
        "analytics_rules",
        "anomaly_columns_required_for_supported_indicators",
        key="required_suffixes",
    )

    if tuple(rule_trend_suffixes) != EXPECTED_TREND_SUFFIXES:
        state.add_error(
            "analytics_trend_suffix_rules_static",
            "Trend suffix rule does not match expected suffixes.",
            {
                "actual": rule_trend_suffixes,
                "expected": list(EXPECTED_TREND_SUFFIXES),
            },
        )
    else:
        state.add_info(
            "analytics_trend_suffix_rules_static",
            "Trend suffix rule matches expected suffixes.",
            {"suffixes": rule_trend_suffixes},
        )

    if tuple(rule_anomaly_suffixes) != EXPECTED_ANOMALY_SUFFIXES:
        state.add_error(
            "analytics_anomaly_suffix_rules_static",
            "Anomaly suffix rule does not match expected suffixes.",
            {
                "actual": rule_anomaly_suffixes,
                "expected": list(EXPECTED_ANOMALY_SUFFIXES),
            },
        )
    else:
        state.add_info(
            "analytics_anomaly_suffix_rules_static",
            "Anomaly suffix rule matches expected suffixes.",
            {"suffixes": rule_anomaly_suffixes},
        )

    required_key_columns = set(
        get_rule_columns(
            rules,
            "analytics_rules",
            "required_key_columns",
            key="columns",
        )
    )

    for table_name in ANALYTICS_TIME_SERIES_TABLES:
        table_spec = get_section_table_spec(table_contract, "analytics", table_name)

        if not table_spec:
            state.add_error(
                "analytics_table_contract_exists",
                f"{table_name} is missing in table_contract.yaml.",
                {"table": table_name},
            )
            continue

        table_columns = get_table_columns(table_spec)
        required_suffixes = table_spec.get("required_suffixes")

        if not table_columns:
            state.add_warning(
                "analytics_required_key_columns_static",
                (
                    f"{table_name} does not declare concrete columns or required_columns "
                    "in table_contract.yaml, so key columns cannot be statically verified."
                ),
                {
                    "table": table_name,
                    "required_columns": sorted(required_key_columns),
                    "table_columns_declared": False,
                },
            )
        else:
            missing_key_columns = sorted(required_key_columns - table_columns)

            if missing_key_columns:
                state.add_error(
                    "analytics_required_key_columns_static",
                    f"{table_name} is missing required key columns.",
                    {"table": table_name, "missing_columns": missing_key_columns},
                )
            else:
                state.add_info(
                    "analytics_required_key_columns_static",
                    f"{table_name} key columns are statically verified.",
                    {
                        "table": table_name,
                        "required_columns": sorted(required_key_columns),
                        "table_columns_declared": True,
                    },
                )

        expected_columns = expected_columns_by_table.get(table_name, set())

        if table_columns:
            missing_analytics_columns = sorted(expected_columns - table_columns)

            for column in missing_analytics_columns:
                item = {
                    "table": table_name,
                    "column": column,
                }
                state.mismatch_report["analytics_missing_columns"].append(item)
                state.add_error(
                    "analytics_expected_column_static",
                    f"{table_name} is missing expected analytics column {column}.",
                    item,
                )
        elif isinstance(required_suffixes, list):
            missing_suffixes = sorted(set(EXPECTED_ANALYTICS_SUFFIXES) - set(required_suffixes))

            if missing_suffixes:
                item = {
                    "table": table_name,
                    "missing_suffixes": missing_suffixes,
                }
                state.mismatch_report["analytics_missing_columns"].append(item)
                state.add_error(
                    "analytics_required_suffixes_static",
                    f"{table_name} is missing required analytics suffixes.",
                    item,
                )
            else:
                state.add_info(
                    "analytics_required_suffixes_static",
                    f"{table_name} declares required analytics suffixes.",
                    {
                        "table": table_name,
                        "required_suffixes": required_suffixes,
                    },
                )
        else:
            state.add_warning(
                "analytics_columns_static",
                (
                    f"{table_name} does not declare concrete columns or "
                    "required_suffixes. Runtime data audit will need to verify columns later."
                ),
                {"table": table_name, "expected_columns_count": len(expected_columns)},
            )

    cluster_spec = get_section_table_spec(
        table_contract,
        "analytics",
        ANALYTICS_CLUSTER_TABLE,
    )

    if not cluster_spec:
        state.add_error(
            "analytics_cluster_contract_exists",
            "analytics_clusters is missing in table_contract.yaml.",
            {"table": ANALYTICS_CLUSTER_TABLE},
        )
        return

    cluster_columns = get_table_columns(cluster_spec)
    cluster_grain = get_table_grain(cluster_spec)

    expected_cluster_key_columns = {"country_code", "year"}
    expected_cluster_business_columns = {
        "country",
        "cluster_id",
        "latest_valid_year",
    }
    expected_cluster_metadata_columns = {
        "run_id",
        "run_date",
        "loaded_at",
    }

    missing_cluster_key_columns = sorted(expected_cluster_key_columns - cluster_columns)
    missing_cluster_business_columns = sorted(
        expected_cluster_business_columns - cluster_columns
    )
    missing_cluster_metadata_columns = sorted(
        expected_cluster_metadata_columns - cluster_columns
    )

    if cluster_grain != ["country_code", "year"]:
        item = {
            "table": ANALYTICS_CLUSTER_TABLE,
            "actual_grain": cluster_grain,
            "expected_grain": ["country_code", "year"],
        }
        state.mismatch_report["cluster_mismatches"].append(item)
        state.add_error(
            "analytics_cluster_grain_static",
            "analytics_clusters grain must be country_code + year.",
            item,
        )
    else:
        state.add_info(
            "analytics_cluster_grain_static",
            "analytics_clusters grain is country_code + year.",
            {"grain": cluster_grain},
        )

    for column in missing_cluster_key_columns:
        item = {
            "table": ANALYTICS_CLUSTER_TABLE,
            "column": column,
            "column_group": "key",
        }
        state.mismatch_report["cluster_mismatches"].append(item)
        state.add_error(
            "analytics_cluster_required_columns_static",
            f"analytics_clusters is missing key column {column}.",
            item,
        )

    for column in missing_cluster_business_columns:
        item = {
            "table": ANALYTICS_CLUSTER_TABLE,
            "column": column,
            "column_group": "business",
        }
        state.mismatch_report["analytics_missing_columns"].append(item)
        state.mismatch_report["cluster_mismatches"].append(item)
        state.add_error(
            "analytics_cluster_required_columns_static",
            f"analytics_clusters is missing business column {column}.",
            item,
        )

    for column in missing_cluster_metadata_columns:
        state.add_warning(
            "analytics_cluster_cloud_metadata_deferred_static",
            (
                f"analytics_clusters is missing cloud metadata column {column}. "
                "This is static/deferred in live warehouse validation if cloud metadata is not applied yet."
            ),
            {
                "table": ANALYTICS_CLUSTER_TABLE,
                "column": column,
                "required_when": "cloud_metadata_available",
            },
        )

    latest_valid_year_required = get_rule_columns(
        rules,
        "analytics_rules",
        "cluster_latest_valid_year_required",
        key="required_columns",
    )

    if "latest_valid_year" not in latest_valid_year_required:
        item = {
            "table": ANALYTICS_CLUSTER_TABLE,
            "column": "latest_valid_year",
            "rule": "cluster_latest_valid_year_required",
        }
        state.mismatch_report["cluster_mismatches"].append(item)
        state.add_error(
            "analytics_cluster_latest_valid_year_rule_static",
            "data_quality_rules.yaml must require latest_valid_year for analytics_clusters.",
            item,
        )
    else:
        state.add_info(
            "analytics_cluster_latest_valid_year_rule_static",
            "data_quality_rules.yaml requires latest_valid_year for analytics_clusters.",
            {"required_columns": latest_valid_year_required},
        )

    cluster_indicators = sorted(
        code
        for code, entry in public_indicators.items()
        if entry.get("used_for_cluster")
    )

    if not cluster_indicators:
        state.add_warning(
            "cluster_indicators_contract_static",
            "No used_for_cluster=true indicators found in indicator_contract.yaml.",
        )
    else:
        state.add_info(
            "cluster_indicators_contract_static",
            "Cluster indicators found in indicator_contract.yaml.",
            {
                "count": len(cluster_indicators),
                "indicators": cluster_indicators,
            },
        )


def audit_bigquery_postgres_rules_deferred(
    state: AuditState,
    rules: dict[str, Any],
) -> None:
    bigquery_rules = rules.get("bigquery_rules")
    postgres_sync_rules = rules.get("postgres_sync_rules")

    if not isinstance(bigquery_rules, dict):
        state.add_warning(
            "bigquery_rules_static_deferred",
            "bigquery_rules section is missing.",
        )
    else:
        state.add_skipped(
            "bigquery_rules_static_deferred",
            (
                "BigQuery live dataset/table validation is deferred in live warehouse validation. "
                "Only config presence is checked now."
            ),
            {"rules": sorted(bigquery_rules.keys())},
        )

    if not isinstance(postgres_sync_rules, dict):
        state.add_warning(
            "postgres_sync_rules_static_deferred",
            "postgres_sync_rules section is missing.",
        )
    else:
        state.add_skipped(
            "postgres_sync_rules_static_deferred",
            (
                "PostgreSQL sync validation is deferred in live warehouse validation. "
                "No BigQuery/PostgreSQL live connection is attempted."
            ),
            {"rules": sorted(postgres_sync_rules.keys())},
        )


def build_data_quality_report(state: AuditState) -> dict[str, Any]:
    status = "failed" if state.errors else "passed"

    return {
        "status": status,
        "summary": {
            "errors": len(state.errors),
            "warnings": len(state.warnings),
            "checks": len(state.checks),
            "info": len(state.info),
        },
        "checks": state.checks,
        "errors": state.errors,
        "warnings": state.warnings,
        "info": state.info,
    }


def finalize_mismatch_report(state: AuditState) -> dict[str, Any]:
    mismatch_keys = [
        "missing_in_silver",
        "missing_in_gold",
        "unknown_silver_indicators",
        "unknown_gold_public_columns",
        "analytics_missing_columns",
        "cluster_mismatches",
    ]

    has_mismatches = any(state.mismatch_report[key] for key in mismatch_keys)
    state.mismatch_report["status"] = "failed" if has_mismatches else "passed"
    return state.mismatch_report


def run_audit(
    silver_path: Path | None = None,
    gold_dir: Path | None = None,
    analytics_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = AuditState()

    audit_runtime_data_paths(
        state,
        silver_path=silver_path,
        gold_dir=gold_dir,
        analytics_dir=analytics_dir,
    )

    indicator_contract, table_contract, rules = audit_required_files(state)

    indicators: dict[str, dict[str, Any]] = {}

    if indicator_contract:
        try:
            indicators = extract_indicator_entries(indicator_contract)
            state.add_info(
                "indicator_contract_load_entries",
                "Loaded indicator entries from indicator_contract.yaml.",
                {"count": len(indicators)},
            )
        except Exception as exc:
            state.add_error(
                "indicator_contract_load_entries",
                f"Cannot extract indicator entries: {exc}",
            )

    if rules:
        audit_rules_defaults(state, rules)

    if indicators and table_contract and rules:
        audit_contract_rules_consistency_static(
            state,
            indicators,
            table_contract,
            rules,
        )

    if indicators:
        audit_indicator_contract_shape(state, indicators)

    if indicators and rules:
        audit_no_interpolate_policy(state, indicators, rules)

    if table_contract and rules:
        audit_silver_contract_static(state, table_contract, rules)

    if indicators and table_contract and rules:
        audit_gold_contract_static(state, indicators, table_contract, rules)
        audit_analytics_contract_static(state, indicators, table_contract, rules)

    if rules:
        audit_bigquery_postgres_rules_deferred(state, rules)

    data_quality_report = build_data_quality_report(state)
    mismatch_report = finalize_mismatch_report(state)

    return data_quality_report, mismatch_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit data quality contract/rules alignment and write live warehouse validation reports."
        )
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 after writing reports. Useful while reviewing first audit output.",
    )
    parser.add_argument(
        "--json-indent",
        type=int,
        default=2,
        help="JSON indent for generated reports. Default: 2.",
    )
    parser.add_argument(
        "--silver-path",
        default=None,
        help=(
            "Optional local path to concrete Silver output file or directory. "
            "Content checks are wired in a later step."
        ),
    )
    parser.add_argument(
        "--gold-dir",
        default=None,
        help=(
            "Optional local directory containing concrete Gold outputs. "
            "Content checks are wired in a later step."
        ),
    )
    parser.add_argument(
        "--analytics-dir",
        default=None,
        help=(
            "Optional local directory containing concrete Analytics outputs. "
            "Content checks are wired in a later step."
        ),
    )
    parser.add_argument(
        "--data-quality-report",
        default=str(DATA_QUALITY_REPORT_PATH),
        help="Path to data quality report JSON.",
    )
    parser.add_argument(
        "--indicator-mismatch-report",
        default=str(INDICATOR_MISMATCH_REPORT_PATH),
        help="Path to indicator mismatch report JSON.",
    )
    args = parser.parse_args()

    silver_path = resolve_repo_path(args.silver_path)
    gold_dir = resolve_repo_path(args.gold_dir)
    analytics_dir = resolve_repo_path(args.analytics_dir)
    data_quality_report_path = resolve_repo_path(args.data_quality_report) or DATA_QUALITY_REPORT_PATH
    indicator_mismatch_report_path = (
        resolve_repo_path(args.indicator_mismatch_report) or INDICATOR_MISMATCH_REPORT_PATH
    )

    data_quality_report, mismatch_report = run_audit(
        silver_path=silver_path,
        gold_dir=gold_dir,
        analytics_dir=analytics_dir,
    )

    write_json(data_quality_report_path, data_quality_report, indent=args.json_indent)
    write_json(indicator_mismatch_report_path, mismatch_report, indent=args.json_indent)

    print("")
    print("=== Data Quality Audit ===")
    print(f"Status: {data_quality_report['status']}")
    print("")
    print("Reports:")
    print(f"  wrote: {format_path_for_report(data_quality_report_path)}")
    print(f"  wrote: {format_path_for_report(indicator_mismatch_report_path)}")
    print("")
    print("Summary:")
    print(f"  checks:   {data_quality_report['summary']['checks']}")
    print(f"  errors:   {data_quality_report['summary']['errors']}")
    print(f"  warnings: {data_quality_report['summary']['warnings']}")
    print(f"  info:     {data_quality_report['summary']['info']}")
    print("")

    if args.no_fail:
        return 0

    return 1 if data_quality_report["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
