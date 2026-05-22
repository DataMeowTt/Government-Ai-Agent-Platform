from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: PyYAML. Install with: pip install pyyaml"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]

INDICATOR_CONTRACT_PATH = ROOT / "contracts" / "indicator_contract.yaml"
TABLE_CONTRACT_PATH = ROOT / "contracts" / "table_contract.yaml"

ANALYTICS_WORKER_OUT = (
    ROOT / "services" / "analytics-worker" / "src" / "generated" / "indicator_contract.py"
)
AI_AGENT_OUT = (
    ROOT / "services" / "ai-agent-service" / "app" / "catalog" / "generated_indicator_catalog.py"
)
BACKEND_OUT = ROOT / "server" / "src" / "generated" / "indicator-contract.ts"
BIGQUERY_SQL_OUT = ROOT / "sql" / "bigquery" / "generated_create_tables.sql"

ANALYTICS_REQUIRED_SUFFIXES = (
    "_actual",
    "_trend",
    "_residual",
    "_slope",
    "_intercept",
    "_r2",
    "_anomaly_score",
)

DEFAULT_CLUSTER_TARGET_YEARS = (2000, 2010, 2020, 2025)

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


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise SystemExit(f"YAML root must be a mapping: {path}")

    return data


def json_dumps(data: Any, indent: int = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=True)


def py_json_literal(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def extract_indicator_entries(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Supports both shapes:

    1) indicators:
         govdebt_GDP: {...}

    2) govdebt_GDP: {...}
       inflation_cpi: {...}

    This keeps the generator tolerant while still failing if no indicator entries exist.
    """
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
            raise SystemExit(f"Indicator entry has empty code: {key}")

        entry = dict(value)
        entry["code"] = code
        indicators[code] = normalize_indicator_entry(entry)

    if not indicators:
        raise SystemExit(
            "No indicator entries found in contracts/indicator_contract.yaml"
        )

    return indicators


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


def get_aliases(entry: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for value in (
        entry.get("code"),
        entry.get("name_vi"),
        entry.get("name_en"),
        *(entry.get("aliases_vi") or []),
        *(entry.get("aliases_en") or []),
    ):
        text = str(value or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    return aliases


def get_analytics_indicators_by_gold_table(
    indicators: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}

    for code, entry in indicators.items():
        if not is_public_indicator(entry):
            continue
        if not (entry.get("supports_trend") or entry.get("supports_anomaly")):
            continue

        gold_table = entry.get("gold_table")
        if not gold_table:
            continue

        result.setdefault(str(gold_table), []).append(code)

    return {
        table: sorted(codes)
        for table, codes in sorted(result.items())
    }


def get_cluster_indicators(indicators: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        code
        for code, entry in indicators.items()
        if is_public_indicator(entry) and bool(entry.get("used_for_cluster"))
    )


def get_no_interpolate_indicators(indicators: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        code
        for code, entry in indicators.items()
        if entry.get("imputation_policy") == "no_interpolate"
    )


def build_public_indicator_payload(
    indicators: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    public = get_public_indicators(indicators)
    payload: dict[str, dict[str, Any]] = {}

    for code, entry in public.items():
        payload[code] = {
            "code": code,
            "name_vi": entry.get("name_vi") or "",
            "name_en": entry.get("name_en") or "",
            "category": entry.get("category") or "",
            "unit": entry.get("unit") or "",
            "gold_table": entry.get("gold_table"),
            "gold_column": entry.get("gold_column") or code,
            "analytics_table": (
                f"analytics_{entry.get('gold_table')}"
                if entry.get("supports_trend") or entry.get("supports_anomaly")
                else None
            ),
            "supports_raw": bool(entry.get("supports_raw")),
            "supports_compare": bool(entry.get("supports_compare")),
            "supports_ranking": bool(entry.get("supports_ranking")),
            "supports_coverage": bool(entry.get("supports_coverage")),
            "supports_trend": bool(entry.get("supports_trend")),
            "supports_anomaly": bool(entry.get("supports_anomaly")),
            "used_for_cluster": bool(entry.get("used_for_cluster")),
            "description_vi": entry.get("description_vi") or "",
            "description_en": entry.get("description_en") or "",
            "aliases": get_aliases(entry),
            "source_indicator": entry.get("source_indicator"),
            "source_priority": list(entry.get("source_priority") or []),
            "imputation_policy": entry.get("imputation_policy"),
            "null_policy": entry.get("null_policy"),
            "value_type": entry.get("value_type"),
        }

    return dict(sorted(payload.items()))


def build_full_contract_payload(
    indicators: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    public_payload = build_public_indicator_payload(indicators)

    return {
        "public_indicators": public_payload,
        "technical_entries": {
            code: entry
            for code, entry in sorted(get_technical_entries(indicators).items())
        },
        "analytics_indicators_by_gold_table": get_analytics_indicators_by_gold_table(
            indicators
        ),
        "cluster_indicators": get_cluster_indicators(indicators),
        "no_interpolate_indicators": get_no_interpolate_indicators(indicators),
        "analytics_required_suffixes": list(ANALYTICS_REQUIRED_SUFFIXES),
        "cluster_target_years": list(DEFAULT_CLUSTER_TARGET_YEARS),
    }


def render_analytics_worker_artifact(payload: dict[str, Any]) -> str:
    public_json = py_json_literal(payload["public_indicators"])
    technical_json = py_json_literal(payload["technical_entries"])
    analytics_json = py_json_literal(payload["analytics_indicators_by_gold_table"])
    cluster_json = py_json_literal(payload["cluster_indicators"])
    no_interp_json = py_json_literal(payload["no_interpolate_indicators"])
    suffixes_json = py_json_literal(payload["analytics_required_suffixes"])
    years_json = py_json_literal(payload["cluster_target_years"])

    return f'''# -*- coding: utf-8 -*-
"""
Generated from contracts/indicator_contract.yaml.

Do not edit this file manually.
Run: python scripts/generate_contract_artifacts.py
"""

from __future__ import annotations

import json
from typing import Any


PUBLIC_INDICATORS: dict[str, dict[str, Any]] = json.loads(r''' + "'''" + public_json + "'''" + f''')
TECHNICAL_ENTRIES: dict[str, dict[str, Any]] = json.loads(r''' + "'''" + technical_json + "'''" + f''')
TABLES_INDICATORS: dict[str, list[str]] = json.loads(r''' + "'''" + analytics_json + "'''" + f''')
ANALYTICS_INDICATORS_BY_GOLD_TABLE = TABLES_INDICATORS

ANALYTICS_REQUIRED_SUFFIXES: tuple[str, ...] = tuple(json.loads(r''' + "'''" + suffixes_json + "'''" + f'''))
ANALYTICS_SUFFIXES: tuple[str, ...] = tuple(
    suffix[1:] if suffix.startswith("_") else suffix
    for suffix in ANALYTICS_REQUIRED_SUFFIXES
)

INDICATORS_FOR_CLUSTER: list[str] = json.loads(r''' + "'''" + cluster_json + "'''" + f''')
CLUSTER_INDICATORS: tuple[str, ...] = tuple(INDICATORS_FOR_CLUSTER)
CLUSTER_TARGET_YEARS: tuple[int, ...] = tuple(json.loads(r''' + "'''" + years_json + "'''" + f'''))

NO_INTERPOLATE_INDICATORS: tuple[str, ...] = tuple(json.loads(r''' + "'''" + no_interp_json + "'''" + f'''))


def get_public_indicator_codes() -> list[str]:
    return list(PUBLIC_INDICATORS.keys())


def get_analytics_columns(indicator_code: str) -> list[str]:
    return [
        f"{{indicator_code}}{{suffix}}"
        for suffix in ANALYTICS_REQUIRED_SUFFIXES
    ]


def get_analytics_table_for_indicator(indicator_code: str) -> str | None:
    indicator = PUBLIC_INDICATORS.get(indicator_code)
    if not indicator:
        return None
    return indicator.get("analytics_table")


def indicator_has_analytics(indicator_code: str) -> bool:
    return get_analytics_table_for_indicator(indicator_code) is not None
'''


def render_ai_agent_catalog_artifact(payload: dict[str, Any]) -> str:
    public_json = py_json_literal(payload["public_indicators"])
    analytics_json = py_json_literal(payload["analytics_indicators_by_gold_table"])
    cluster_json = py_json_literal(payload["cluster_indicators"])
    suffixes_json = py_json_literal(payload["analytics_required_suffixes"])

    return f'''# -*- coding: utf-8 -*-
"""
Generated from contracts/indicator_contract.yaml.

Do not edit this file manually.
Run: python scripts/generate_contract_artifacts.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalIndicator:
    code: str
    name_vi: str
    name_en: str
    category: str
    unit: str
    gold_table: str | None
    gold_column: str
    analytics_table: str | None = None
    supports_raw: bool = True
    supports_compare: bool = True
    supports_ranking: bool = True
    supports_coverage: bool = True
    supports_trend: bool = False
    supports_anomaly: bool = False
    used_for_cluster: bool = False
    description_vi: str = ""
    description_en: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndicatorAliasMatch:
    indicator: CanonicalIndicator
    matched_alias: str
    confidence: float


_RAW_INDICATORS: dict[str, dict] = json.loads(r''' + "'''" + public_json + "'''" + f''')
ANALYTICS_INDICATORS_BY_GOLD_TABLE: dict[str, tuple[str, ...]] = {{
    table: tuple(codes)
    for table, codes in json.loads(r''' + "'''" + analytics_json + "'''" + f''').items()
}}
ANALYTICS_REQUIRED_SUFFIXES: tuple[str, ...] = tuple(json.loads(r''' + "'''" + suffixes_json + "'''" + f'''))
ANALYTICS_SUFFIXES: tuple[str, ...] = tuple(
    suffix[1:] if suffix.startswith("_") else suffix
    for suffix in ANALYTICS_REQUIRED_SUFFIXES
)
CLUSTER_INDICATORS: tuple[str, ...] = tuple(json.loads(r''' + "'''" + cluster_json + "'''" + f'''))


def _to_indicator(row: dict) -> CanonicalIndicator:
    return CanonicalIndicator(
        code=row["code"],
        name_vi=row.get("name_vi") or "",
        name_en=row.get("name_en") or "",
        category=row.get("category") or "",
        unit=row.get("unit") or "",
        gold_table=row.get("gold_table"),
        gold_column=row.get("gold_column") or row["code"],
        analytics_table=row.get("analytics_table"),
        supports_raw=bool(row.get("supports_raw")),
        supports_compare=bool(row.get("supports_compare")),
        supports_ranking=bool(row.get("supports_ranking")),
        supports_coverage=bool(row.get("supports_coverage")),
        supports_trend=bool(row.get("supports_trend")),
        supports_anomaly=bool(row.get("supports_anomaly")),
        used_for_cluster=bool(row.get("used_for_cluster")),
        description_vi=row.get("description_vi") or "",
        description_en=row.get("description_en") or "",
        aliases=tuple(row.get("aliases") or ()),
    )


INDICATORS: dict[str, CanonicalIndicator] = {{
    code: _to_indicator(row)
    for code, row in _RAW_INDICATORS.items()
}}

AMBIGUOUS_NORMALIZED_ALIASES: set[str] = {{
    "gdp",
    "debt",
    "growth",
    "trade",
    "tax",
}}


def normalize_catalog_text(text: str) -> str:
    normalized = str(text or "").lower().strip().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9%\\s/.-]", " ", normalized)
    normalized = re.sub(r"\\s+", " ", normalized)
    return normalized.strip()


def get_indicator(code: str) -> CanonicalIndicator | None:
    return INDICATORS.get(code)


def list_indicators() -> list[CanonicalIndicator]:
    return list(INDICATORS.values())


def list_indicator_codes() -> list[str]:
    return list(INDICATORS.keys())


def is_supported_indicator(code: str) -> bool:
    return code in INDICATORS


def get_indicator_by_column(
    gold_table: str,
    gold_column: str,
) -> CanonicalIndicator | None:
    for indicator in INDICATORS.values():
        if indicator.gold_table == gold_table and indicator.gold_column == gold_column:
            return indicator
    return None


def _contains_alias(normalized_text: str, normalized_alias: str) -> bool:
    if not normalized_alias or normalized_alias in AMBIGUOUS_NORMALIZED_ALIASES:
        return False

    if len(normalized_alias) <= 3:
        return re.search(rf"(^|\\s){{re.escape(normalized_alias)}}($|\\s)", normalized_text) is not None

    if re.fullmatch(r"[a-z0-9]+", normalized_alias):
        return re.search(rf"(^|\\s){{re.escape(normalized_alias)}}($|\\s)", normalized_text) is not None

    return normalized_alias in normalized_text


def _score_alias(normalized_text: str, alias: str) -> float:
    normalized_alias = normalize_catalog_text(alias)
    if normalized_text == normalized_alias:
        return 1.0
    if not _contains_alias(normalized_text, normalized_alias):
        return 0.0
    return min(0.99, 0.75 + len(normalized_alias) / 240)


def resolve_indicator_aliases(text: str, limit: int = 3) -> list[IndicatorAliasMatch]:
    if limit <= 0:
        return []

    normalized_text = normalize_catalog_text(text)
    matches: list[IndicatorAliasMatch] = []

    for indicator in INDICATORS.values():
        best_score = 0.0
        best_alias = ""
        best_alias_length = 0

        for alias in indicator.aliases:
            normalized_alias = normalize_catalog_text(alias)
            score = _score_alias(normalized_text, alias)
            alias_length = len(normalized_alias)
            if score > best_score or (score == best_score and alias_length > best_alias_length):
                best_score = score
                best_alias = alias
                best_alias_length = alias_length

        if best_score >= 0.75:
            matches.append(
                IndicatorAliasMatch(
                    indicator=indicator,
                    matched_alias=best_alias,
                    confidence=round(best_score, 3),
                )
            )

    matches.sort(
        key=lambda item: (
            item.confidence,
            len(normalize_catalog_text(item.matched_alias)),
        ),
        reverse=True,
    )
    return matches[:limit]


def resolve_indicator_alias(text: str) -> IndicatorAliasMatch | None:
    matches = resolve_indicator_aliases(text, limit=1)
    return matches[0] if matches else None


def get_analytics_columns(code: str) -> list[str]:
    if not indicator_has_analytics(code):
        return []
    return [f"{{code}}{{suffix}}" for suffix in ANALYTICS_REQUIRED_SUFFIXES]


def get_analytics_table_for_indicator(code: str) -> str | None:
    indicator = get_indicator(code)
    return indicator.analytics_table if indicator else None


def indicator_has_analytics(code: str) -> bool:
    return get_analytics_table_for_indicator(code) is not None


def indicator_supports_trend(code: str) -> bool:
    indicator = get_indicator(code)
    return bool(indicator and indicator.supports_trend)


def indicator_supports_anomaly(code: str) -> bool:
    indicator = get_indicator(code)
    return bool(indicator and indicator.supports_anomaly)


def indicator_used_for_cluster(code: str) -> bool:
    indicator = get_indicator(code)
    return bool(indicator and indicator.used_for_cluster)


def get_indicator_analytics_metadata(code: str) -> dict:
    analytics_table = get_analytics_table_for_indicator(code)
    return {{
        "has_analytics": analytics_table is not None,
        "analytics_table": analytics_table,
        "analytics_columns": get_analytics_columns(code),
        "supports_trend": indicator_supports_trend(code),
        "supports_anomaly": indicator_supports_anomaly(code),
        "used_for_cluster": indicator_used_for_cluster(code),
    }}


def get_supported_indicators_compact(max_aliases_per_indicator: int = 8) -> list[dict]:
    return [
        {{
            "code": indicator.code,
            "name_vi": indicator.name_vi,
            "name_en": indicator.name_en,
            "unit": indicator.unit,
            "description_vi": indicator.description_vi,
            "description_en": indicator.description_en,
            "aliases": list(indicator.aliases[:max_aliases_per_indicator]),
            "supports_trend": indicator.supports_trend,
            "supports_anomaly": indicator.supports_anomaly,
        }}
        for indicator in INDICATORS.values()
    ]
'''


def render_backend_artifact(payload: dict[str, Any]) -> str:
    public_payload = payload["public_indicators"]
    indicator_codes = list(public_payload.keys())
    analytics_codes = sorted(
        code
        for table_codes in payload["analytics_indicators_by_gold_table"].values()
        for code in table_codes
    )
    raw_only_codes = sorted(
        code
        for code in indicator_codes
        if code not in set(analytics_codes)
    )

    return f'''/*
 * Generated from contracts/indicator_contract.yaml.
 *
 * Do not edit this file manually.
 * Run: python scripts/generate_contract_artifacts.py
 */

export interface GeneratedIndicatorContract {{
  code: string;
  name_vi: string;
  name_en: string;
  category: string;
  unit: string;
  gold_table: string | null;
  gold_column: string;
  analytics_table: string | null;
  supports_raw: boolean;
  supports_compare: boolean;
  supports_ranking: boolean;
  supports_coverage: boolean;
  supports_trend: boolean;
  supports_anomaly: boolean;
  used_for_cluster: boolean;
  description_vi: string;
  description_en: string;
  aliases: readonly string[];
  source_indicator?: string | null;
  source_priority?: readonly string[];
  imputation_policy?: string | null;
  null_policy?: string | null;
  value_type?: string | null;
}}

export const INDICATOR_CONTRACT = {json_dumps(public_payload, indent=2)} as const;

export const PUBLIC_INDICATOR_CODES = {json_dumps(indicator_codes, indent=2)} as const;

export const ANALYTICS_INDICATOR_CODES = {json_dumps(analytics_codes, indent=2)} as const;

export const RAW_ONLY_INDICATOR_CODES = {json_dumps(raw_only_codes, indent=2)} as const;

export const ANALYTICS_INDICATORS_BY_GOLD_TABLE = {json_dumps(payload["analytics_indicators_by_gold_table"], indent=2)} as const;

export const CLUSTER_INDICATORS = {json_dumps(payload["cluster_indicators"], indent=2)} as const;

export const TECHNICAL_ENTRIES = {json_dumps(payload["technical_entries"], indent=2)} as const;

export const ANALYTICS_REQUIRED_SUFFIXES = {json_dumps(payload["analytics_required_suffixes"], indent=2)} as const;

export type IndicatorCode = keyof typeof INDICATOR_CONTRACT;

export function listIndicators(): GeneratedIndicatorContract[] {{
  return Object.values(INDICATOR_CONTRACT) as unknown as GeneratedIndicatorContract[];
}}

export function getIndicator(code: string): GeneratedIndicatorContract | undefined {{
  return (INDICATOR_CONTRACT as unknown as Record<string, GeneratedIndicatorContract>)[code];
}}

export function isPublicIndicator(code: string): boolean {{
  return Boolean(getIndicator(code));
}}
'''


def extract_table_entries(raw_table_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return

        for key, value in node.items():
            if isinstance(value, dict) and isinstance(value.get("columns"), (dict, list)):
                tables[str(key)] = value
            elif isinstance(value, dict):
                visit(value)

    visit(raw_table_contract)
    return tables


def normalize_column_map(columns: Any) -> dict[str, dict[str, Any]]:
    if isinstance(columns, dict):
        result = {}
        for name, spec in columns.items():
            if isinstance(spec, dict):
                result[str(name)] = dict(spec)
            else:
                result[str(name)] = {"type": str(spec)}
        return result

    if isinstance(columns, list):
        result = {}
        for item in columns:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("column") or item.get("column_name")
            if not name:
                continue
            spec = dict(item)
            spec.pop("name", None)
            spec.pop("column", None)
            spec.pop("column_name", None)
            result[str(name)] = spec
        return result

    return {}


def bigquery_type(raw_type: Any, value_type: Any = None) -> str:
    text = str(raw_type or value_type or "").strip().lower()

    mapping = {
        "str": "STRING",
        "string": "STRING",
        "text": "STRING",
        "varchar": "STRING",
        "int": "INTEGER",
        "integer": "INTEGER",
        "int64": "INTEGER",
        "year": "INTEGER",
        "float": "FLOAT64",
        "float64": "FLOAT64",
        "double": "FLOAT64",
        "numeric": "FLOAT64",
        "number": "FLOAT64",
        "decimal": "FLOAT64",
        "bool": "BOOL",
        "boolean": "BOOL",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
        "datetime": "DATETIME",
        "json": "JSON",
        "object": "JSON",
    }

    return mapping.get(text, "FLOAT64")


def dataset_for_table(table_name: str) -> str:
    if table_name.startswith("silver_"):
        return "gov_ai_silver"
    if table_name.startswith("gold_"):
        return "gov_ai_gold"
    if table_name.startswith("analytics_"):
        return "gov_ai_analytics"
    return "gov_ai_ops"


def quote_bq_name(name: str) -> str:
    return f"`{name}`"


def render_column_sql(name: str, spec: dict[str, Any]) -> str:
    col_type = bigquery_type(spec.get("type"), spec.get("value_type"))
    nullable = bool(spec.get("nullable", True))
    not_null = "" if nullable else " NOT NULL"
    return f"  {quote_bq_name(name)} {col_type}{not_null}"


def build_fallback_gold_tables(
    indicators: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}

    base_columns = {
        "country_code": {"type": "STRING", "nullable": False},
        "country": {"type": "STRING", "nullable": True},
        "year": {"type": "INTEGER", "nullable": False},
        "income_group": {"type": "STRING", "nullable": True},
        "development_group": {"type": "STRING", "nullable": True},
    }

    for code, entry in indicators.items():
        gold_table = entry.get("gold_table")
        gold_column = entry.get("gold_column") or code

        if gold_table:
            table = tables.setdefault(str(gold_table), {"columns": dict(base_columns)})
            table["columns"][str(gold_column)] = {
                "type": bigquery_type(None, entry.get("value_type")),
                "nullable": True,
            }

        for location in entry.get("additional_gold_locations") or []:
            if not isinstance(location, dict):
                continue
            extra_table = location.get("gold_table")
            extra_column = location.get("gold_column") or gold_column
            if not extra_table:
                continue
            table = tables.setdefault(str(extra_table), {"columns": dict(base_columns)})
            table["columns"][str(extra_column)] = {
                "type": bigquery_type(None, entry.get("value_type")),
                "nullable": True,
            }

        for target_table in entry.get("applies_to_gold_tables") or []:
            table = tables.setdefault(str(target_table), {"columns": dict(base_columns)})
            table["columns"][str(gold_column)] = {
                "type": bigquery_type(None, entry.get("value_type")),
                "nullable": True,
            }

    return tables


BQ_TYPE_ALIASES = {
    "FLOAT": "FLOAT64",
    "DOUBLE": "FLOAT64",
    "DOUBLE PRECISION": "FLOAT64",
    "INTEGER": "INT64",
    "INT": "INT64",
    "BIGINT": "INT64",
    "BOOLEAN": "BOOL",
    "TEXT": "STRING",
    "VARCHAR": "STRING",
    "STRING": "STRING",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
    "DATETIME": "DATETIME",
    "JSON": "JSON",
    "BOOL": "BOOL",
    "FLOAT64": "FLOAT64",
    "INT64": "INT64",
}

BQ_DEFAULT_COLUMN_TYPES = {
    "country_code": "STRING",
    "country": "STRING",
    "year": "INT64",
    "indicator": "STRING",
    "value": "FLOAT64",
    "source": "STRING",
    "run_id": "STRING",
    "run_date": "DATE",
    "loaded_at": "TIMESTAMP",
    "cluster_id": "INT64",
    "latest_valid_year": "INT64",
    "method": "STRING",
    "status": "STRING",
    "source_changed": "BOOL",
    "raw_hashes": "JSON",
    "silver_rows": "INT64",
    "gold_rows": "JSON",
    "analytics_rows": "JSON",
    "started_at": "TIMESTAMP",
    "finished_at": "TIMESTAMP",
    "error_message": "STRING",
    "source_name": "STRING",
    "source_uri": "STRING",
    "snapshot_uri": "STRING",
    "sha256": "STRING",
    "bytes": "INT64",
    "created_at": "TIMESTAMP",
    "job_name": "STRING",
    "duration_seconds": "FLOAT64",
    "check_name": "STRING",
    "severity": "STRING",
    "message": "STRING",
    "details": "JSON",
    "contract_version": "STRING",
    "published_date": "DATE",
}

OPS_TABLES = {
    "source_snapshots": {
        "dataset": "gov_ai_ops",
        "columns": {
            "run_id": {"type": "STRING", "nullable": False},
            "run_date": {"type": "DATE", "nullable": False},
            "source_name": {"type": "STRING", "nullable": False},
            "source_uri": {"type": "STRING", "nullable": True},
            "snapshot_uri": {"type": "STRING", "nullable": True},
            "sha256": {"type": "STRING", "nullable": True},
            "bytes": {"type": "INT64", "nullable": True},
            "status": {"type": "STRING", "nullable": False},
            "created_at": {"type": "TIMESTAMP", "nullable": False},
            "error_message": {"type": "STRING", "nullable": True},
        },
    },
    "job_logs": {
        "dataset": "gov_ai_ops",
        "columns": {
            "run_id": {"type": "STRING", "nullable": False},
            "run_date": {"type": "DATE", "nullable": False},
            "job_name": {"type": "STRING", "nullable": False},
            "status": {"type": "STRING", "nullable": False},
            "started_at": {"type": "TIMESTAMP", "nullable": False},
            "finished_at": {"type": "TIMESTAMP", "nullable": True},
            "duration_seconds": {"type": "FLOAT64", "nullable": True},
            "error_message": {"type": "STRING", "nullable": True},
        },
    },
    "data_quality_results": {
        "dataset": "gov_ai_ops",
        "columns": {
            "run_id": {"type": "STRING", "nullable": False},
            "run_date": {"type": "DATE", "nullable": False},
            "check_name": {"type": "STRING", "nullable": False},
            "severity": {"type": "STRING", "nullable": False},
            "status": {"type": "STRING", "nullable": False},
            "message": {"type": "STRING", "nullable": True},
            "details": {"type": "JSON", "nullable": True},
            "created_at": {"type": "TIMESTAMP", "nullable": False},
        },
    },
    "indicator_contract_versions": {
        "dataset": "gov_ai_ops",
        "columns": {
            "contract_version": {"type": "STRING", "nullable": False},
            "published_date": {"type": "DATE", "nullable": False},
            "sha256": {"type": "STRING", "nullable": True},
            "source_uri": {"type": "STRING", "nullable": True},
            "created_at": {"type": "TIMESTAMP", "nullable": False},
        },
    },
}


def to_bigquery_type(value: Any) -> str:
    normalized = str(value or "STRING").strip().upper()
    return BQ_TYPE_ALIASES.get(normalized, normalized)


def default_column_spec(column_name: str, nullable: bool = True) -> dict[str, Any]:
    return {
        "type": BQ_DEFAULT_COLUMN_TYPES.get(column_name, "STRING"),
        "nullable": nullable,
    }


def normalize_contract_table_spec(table_spec: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(table_spec)
    columns = normalize_column_map(normalized.get("columns"))

    if columns:
        normalized["columns"] = {
            column_name: {
                **column_spec,
                "type": to_bigquery_type(column_spec.get("type")),
                "nullable": bool(column_spec.get("nullable", True)),
            }
            for column_name, column_spec in columns.items()
        }
    else:
        required_columns = normalized.get("required_columns") or normalized.get("grain") or []
        if isinstance(required_columns, list):
            normalized["columns"] = {
                str(column_name): default_column_spec(str(column_name), nullable=False)
                for column_name in required_columns
            }

    return normalized


def merge_table_specs(
    base_spec: dict[str, Any] | None,
    override_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base_spec or {})
    override = normalize_contract_table_spec(override_spec or {})

    for key, value in override.items():
        if key != "columns":
            merged[key] = value

    merged_columns = normalize_column_map(merged.get("columns"))
    override_columns = normalize_column_map(override.get("columns"))

    for column_name, column_spec in override_columns.items():
        merged_columns[column_name] = {
            **column_spec,
            "type": to_bigquery_type(column_spec.get("type")),
            "nullable": bool(column_spec.get("nullable", True)),
        }

    for column_name in override.get("required_columns") or []:
        merged_columns.setdefault(
            str(column_name),
            default_column_spec(str(column_name), nullable=False),
        )

    if merged_columns:
        merged["columns"] = merged_columns

    return merged


def get_bigquery_datasets(raw_table_contract: dict[str, Any]) -> list[str]:
    defaults = ["gov_ai_silver", "gov_ai_gold", "gov_ai_analytics", "gov_ai_ops"]
    warehouse = raw_table_contract.get("warehouse")
    if not isinstance(warehouse, dict):
        return defaults

    bigquery = warehouse.get("bigquery")
    if not isinstance(bigquery, dict):
        return defaults

    datasets = bigquery.get("datasets")
    if not isinstance(datasets, dict):
        return defaults

    values = [str(value) for value in datasets.values() if value]
    return values or defaults


def render_bigquery_partition_sql(
    table_spec: dict[str, Any],
    columns: dict[str, dict[str, Any]],
) -> str | None:
    partition = table_spec.get("partition")

    if isinstance(partition, dict):
        partition_type = str(partition.get("type") or "").strip().lower()
        column = str(partition.get("column") or "").strip()

        if column and column in columns and partition_type == "integer_range":
            start = int(partition.get("start", 1980))
            end = int(partition.get("end", 2031))
            interval = int(partition.get("interval", 1))
            inclusive_end = end - interval
            return (
                f"PARTITION BY RANGE_BUCKET(`{column}`, "
                f"GENERATE_ARRAY({start}, {inclusive_end}, {interval}))"
            )

        if column and column in columns and partition_type == "date":
            return f"PARTITION BY `{column}`"

    if "year" in columns:
        return "PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))"

    if "run_date" in columns:
        return "PARTITION BY `run_date`"

    return None


def render_bigquery_cluster_sql(
    table_spec: dict[str, Any],
    columns: dict[str, dict[str, Any]],
) -> str | None:
    raw_cluster = table_spec.get("cluster")
    cluster_columns: list[str] = []

    if isinstance(raw_cluster, list):
        cluster_columns = [
            str(column)
            for column in raw_cluster
            if str(column) in columns
        ]

    if not cluster_columns:
        for column in ("country_code", "indicator", "source", "status"):
            if column in columns:
                cluster_columns.append(column)

    cluster_columns = cluster_columns[:4]

    if not cluster_columns:
        return None

    rendered = ", ".join(f"`{column}`" for column in cluster_columns)
    return f"CLUSTER BY {rendered}"


def render_bigquery_table_options(
    table_spec: dict[str, Any],
    columns: dict[str, dict[str, Any]],
) -> list[str]:
    options: list[str] = []

    partition_sql = render_bigquery_partition_sql(table_spec, columns)
    if partition_sql:
        options.append(partition_sql)

    cluster_sql = render_bigquery_cluster_sql(table_spec, columns)
    if cluster_sql:
        options.append(cluster_sql)

    return options


def build_analytics_tables(
    payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}

    for gold_table, codes in payload["analytics_indicators_by_gold_table"].items():
        analytics_table = f"analytics_{gold_table}"
        columns: dict[str, dict[str, Any]] = {
            "country_code": {"type": "STRING", "nullable": False},
            "country": {"type": "STRING", "nullable": False},
            "year": {"type": "INT64", "nullable": False},
        }

        for code in codes:
            for suffix in ANALYTICS_REQUIRED_SUFFIXES:
                columns[f"{code}{suffix}"] = {
                    "type": "FLOAT64",
                    "nullable": True,
                }

        columns["run_id"] = {"type": "STRING", "nullable": False}
        columns["run_date"] = {"type": "DATE", "nullable": False}
        columns["loaded_at"] = {"type": "TIMESTAMP", "nullable": False}

        tables[analytics_table] = {
            "dataset": "gov_ai_analytics",
            "columns": columns,
        }

    tables["analytics_clusters"] = {
        "dataset": "gov_ai_analytics",
        "columns": {
            "country_code": {"type": "STRING", "nullable": False},
            "country": {"type": "STRING", "nullable": False},
            "year": {"type": "INT64", "nullable": False},
            "cluster_id": {"type": "INT64", "nullable": False},
            "latest_valid_year": {"type": "INT64", "nullable": False},
            "run_id": {"type": "STRING", "nullable": False},
            "run_date": {"type": "DATE", "nullable": False},
            "loaded_at": {"type": "TIMESTAMP", "nullable": False},
        },
    }

    return tables


def render_bigquery_sql(
    indicators: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    raw_table_contract: dict[str, Any],
) -> str:
    contract_tables = extract_table_entries(raw_table_contract)
    fallback_gold_tables = build_fallback_gold_tables(indicators)
    analytics_tables = build_analytics_tables(payload)

    all_tables: dict[str, dict[str, Any]] = {}
    all_tables.update(fallback_gold_tables)
    all_tables.update(analytics_tables)
    all_tables.update(OPS_TABLES)

    for table_name, table_spec in contract_tables.items():
        all_tables[table_name] = merge_table_specs(
            all_tables.get(table_name),
            table_spec,
        )

    lines: list[str] = [
        "-- Generated from contracts/*.yaml.",
        "-- Do not edit manually.",
        "-- Run: python scripts/generate_contract_artifacts.py",
        "",
    ]

    for dataset in get_bigquery_datasets(raw_table_contract):
        lines.append(f"CREATE SCHEMA IF NOT EXISTS `{dataset}`;")

    lines.append("")

    for table_name in sorted(all_tables.keys()):
        table_spec = normalize_contract_table_spec(all_tables[table_name])
        columns = normalize_column_map(table_spec.get("columns"))

        if not columns:
            continue

        dataset = str(table_spec.get("dataset") or dataset_for_table(table_name))
        column_lines = [
            render_column_sql(column_name, column_spec)
            for column_name, column_spec in columns.items()
        ]

        table_options = render_bigquery_table_options(table_spec, columns)

        lines.append(f"CREATE TABLE IF NOT EXISTS `{dataset}.{table_name}` (")
        lines.append(",\n".join(column_lines))
        lines.append(")")

        if table_options:
            lines.extend(table_options)

        lines.append(";")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote: {path.relative_to(ROOT)}")

def run_preflight_validation(skip_validate: bool) -> None:
    if skip_validate:
        print("skip: preflight contract validation disabled by --skip-validate")
        return

    validator_path = ROOT / "scripts" / "validate_indicator_contract.py"
    if not validator_path.exists():
        raise SystemExit(
            f"Missing validator script: {validator_path.relative_to(ROOT)}"
        )

    print("running preflight: python scripts/validate_indicator_contract.py")
    completed = subprocess.run(
        [sys.executable, str(validator_path)],
        cwd=ROOT,
        check=False,
    )

    if completed.returncode != 0:
        raise SystemExit(
            "Preflight contract validation failed. "
            "Fix contracts/indicator_contract.yaml first, or rerun with --skip-validate only for debugging."
        )


def generate(skip_validate: bool = False) -> None:
    run_preflight_validation(skip_validate)

    raw_indicator_contract = load_yaml(INDICATOR_CONTRACT_PATH)
    raw_table_contract = load_yaml(TABLE_CONTRACT_PATH)

    indicators = extract_indicator_entries(raw_indicator_contract)
    payload = build_full_contract_payload(indicators)

    write_file(ANALYTICS_WORKER_OUT, render_analytics_worker_artifact(payload))
    write_file(AI_AGENT_OUT, render_ai_agent_catalog_artifact(payload))
    write_file(BACKEND_OUT, render_backend_artifact(payload))
    write_file(
        BIGQUERY_SQL_OUT,
        render_bigquery_sql(indicators, payload, raw_table_contract),
    )

    print("")
    print("=== Contract Artifact Generation ===")
    print("Status: passed")
    print("")
    print("Summary:")
    print(f"  total_entries: {len(indicators)}")
    print(f"  public_indicators: {len(payload['public_indicators'])}")
    print(f"  technical_entries: {len(payload['technical_entries'])}")
    print(
        "  analytics_indicators: "
        f"{sum(len(v) for v in payload['analytics_indicators_by_gold_table'].values())}"
    )
    print(f"  cluster_indicators: {len(payload['cluster_indicators'])}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate runtime artifacts from contract YAML files."
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help=(
            "Skip preflight contract validation. "
            "Use only for debugging generator output."
        ),
    )
    args = parser.parse_args()
    generate(skip_validate=args.skip_validate)


if __name__ == "__main__":
    main()
