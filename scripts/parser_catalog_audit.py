from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FORBIDDEN_INDICATORS = ("decade", "flag_score", "completeness_score")
PARSER_CONFIG_FILENAMES = (
    "indicator_catalog.v1.json",
    "country_catalog.v1.json",
    "analytics_metadata.v1.json",
    "parser_intents.v1.json",
    "question_families.v1.json",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_existing(path_candidates: list[Path]) -> Path | None:
    for path in path_candidates:
        if path.exists():
            return path
    return None


def _find_parser_config_dir(explicit_dir: Path | None) -> Path | None:
    candidates: list[Path] = []
    if explicit_dir:
        candidates.append(explicit_dir)
    candidates.extend(
        [
            ROOT / "configs",
            ROOT / "services" / "query-agent" / "training" / "v1" / "government-parser-dataset-v1",
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _read_parser_configs_from_dir(config_dir: Path | None) -> tuple[dict[str, Any], dict[str, str]]:
    if config_dir is None:
        return {}, {}

    payload: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for name in PARSER_CONFIG_FILENAMES:
        path = config_dir / name
        if path.exists():
            payload[name] = _load_json(path)
            sources[name] = str(path.relative_to(ROOT))
    return payload, sources


def _read_parser_configs_from_zip(zip_path: Path | None) -> tuple[dict[str, Any], dict[str, str]]:
    if zip_path is None or not zip_path.exists():
        return {}, {}

    payload: dict[str, Any] = {}
    sources: dict[str, str] = {}
    with ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for name in PARSER_CONFIG_FILENAMES:
            zip_member = f"configs/{name}"
            if zip_member not in names:
                continue
            payload[name] = json.loads(zf.read(zip_member).decode("utf-8"))
            sources[name] = f"{zip_path.relative_to(ROOT)}!/{zip_member}"
    return payload, sources


def _extract_contract_public_indicators() -> set[str]:
    contract = _load_yaml(ROOT / "contracts" / "indicator_contract.yaml")
    result: set[str] = set()
    for code, meta in contract.items():
        if not isinstance(meta, dict):
            continue
        if meta.get("public") and not meta.get("technical") and not meta.get("dimension"):
            result.add(str(code))
    return result


def _import_ai_runtime_catalog() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "services" / "ai-agent-service"))
    from app.catalog.analytics_catalog import CLUSTER_TARGET_YEARS
    from app.catalog.generated_indicator_catalog import ANALYTICS_INDICATORS_BY_GOLD_TABLE, INDICATORS
    from app.resolver.country_resolver import COUNTRIES

    return {
        "indicator_codes": set(INDICATORS.keys()),
        "analytics_indicators_by_gold_table": {
            table: set(codes)
            for table, codes in ANALYTICS_INDICATORS_BY_GOLD_TABLE.items()
        },
        "cluster_target_years": list(CLUSTER_TARGET_YEARS),
        "country_codes": set(COUNTRIES.keys()),
    }


def _extract_indicator_codes(indicator_catalog: Any) -> set[str]:
    if not isinstance(indicator_catalog, dict):
        return set()
    items = indicator_catalog.get("indicators") or []
    return {
        str(item.get("code"))
        for item in items
        if isinstance(item, dict) and item.get("code")
    }


def _extract_country_codes(country_catalog: Any) -> set[str]:
    if not isinstance(country_catalog, dict):
        return set()
    items = country_catalog.get("countries") or []
    return {
        str(item.get("code")).upper()
        for item in items
        if isinstance(item, dict) and item.get("code")
    }


def _extract_parser_intents(raw: Any) -> set[str]:
    if isinstance(raw, list):
        return {str(item) for item in raw}
    if isinstance(raw, dict):
        intents = raw.get("intents") or raw.get("allowed_intents") or []
        if isinstance(intents, list):
            return {str(item.get("intent") or item.get("code") or item) for item in intents}
    return set()


def _extract_question_family_intents(raw: Any) -> set[str]:
    if not isinstance(raw, dict):
        return set()
    items = raw.get("families") or []
    intents: set[str] = set()
    for item in items:
        if isinstance(item, dict) and item.get("intent"):
            intents.add(str(item["intent"]))
    return intents


def run_audit(
    parser_config_dir: Path | None,
    parser_artifact_zip: Path | None,
    forbidden_indicators: tuple[str, ...],
) -> dict[str, Any]:
    contract_public = _extract_contract_public_indicators()
    ai_runtime = _import_ai_runtime_catalog()
    ai_public = set(ai_runtime["indicator_codes"])

    config_dir_payload, config_dir_sources = _read_parser_configs_from_dir(parser_config_dir)
    zip_payload, zip_sources = _read_parser_configs_from_zip(parser_artifact_zip)

    parser_payload = dict(zip_payload)
    parser_payload.update(config_dir_payload)
    parser_sources = dict(zip_sources)
    parser_sources.update(config_dir_sources)

    indicator_catalog = parser_payload.get("indicator_catalog.v1.json")
    parser_indicator_codes = _extract_indicator_codes(indicator_catalog)

    country_catalog = parser_payload.get("country_catalog.v1.json")
    parser_country_codes = _extract_country_codes(country_catalog)

    parser_intents = _extract_parser_intents(parser_payload.get("parser_intents.v1.json"))
    family_intents = _extract_question_family_intents(parser_payload.get("question_families.v1.json"))

    forbidden_in_parser = sorted(parser_indicator_codes.intersection(set(forbidden_indicators)))
    parser_only_indicators = sorted(parser_indicator_codes - ai_public)
    missing_in_parser = sorted(ai_public - parser_indicator_codes)
    contract_vs_generated_diff = {
        "contract_public_only": sorted(contract_public - ai_public),
        "generated_public_only": sorted(ai_public - contract_public),
    }

    analytics_metadata = parser_payload.get("analytics_metadata.v1.json") or {}
    parser_cluster_target_years = (
        ((analytics_metadata.get("cluster") or {}).get("target_years")) or []
        if isinstance(analytics_metadata, dict)
        else []
    )
    parser_analytics_tables = (
        (analytics_metadata.get("analytics_tables_indicators") or {})
        if isinstance(analytics_metadata, dict)
        else {}
    )
    parser_analytics_tables = {
        str(table): set(str(code) for code in codes or [])
        for table, codes in parser_analytics_tables.items()
    }
    runtime_analytics_tables = ai_runtime["analytics_indicators_by_gold_table"]
    analytics_table_mismatch: dict[str, Any] = {}
    for table in sorted(set(runtime_analytics_tables.keys()) | set(parser_analytics_tables.keys())):
        runtime_codes = runtime_analytics_tables.get(table, set())
        parser_codes = parser_analytics_tables.get(table, set())
        if runtime_codes != parser_codes:
            analytics_table_mismatch[table] = {
                "runtime_only": sorted(runtime_codes - parser_codes),
                "parser_only": sorted(parser_codes - runtime_codes),
            }

    country_mismatch = {
        "runtime_only": sorted(ai_runtime["country_codes"] - parser_country_codes),
        "parser_only": sorted(parser_country_codes - ai_runtime["country_codes"]),
    }

    ai_supported_intents = {
        "COMPARE_COUNTRIES",
        "RANKING",
        "TIME_SERIES",
        "TREND_ANALYSIS",
        "ANOMALY_DETECTION",
        "COVERAGE",
        "VALUE_LOOKUP",
        "NEED_CLARIFICATION",
        "UNSUPPORTED",
        "OFF_TOPIC",
        "DIRECT_ANSWER",
        "GENERAL_EXPLANATION",
    }
    unsupported_parser_intents = sorted(parser_intents - ai_supported_intents)
    unsupported_question_family_intents = sorted(family_intents - ai_supported_intents)

    return {
        "parser_artifact_available": bool(parser_indicator_codes),
        "parser_artifact_zip_available": bool(zip_payload),
        "parser_config_dir": str(parser_config_dir.relative_to(ROOT)) if parser_config_dir else None,
        "parser_sources": parser_sources,
        "counts": {
            "contract_public_indicators": len(contract_public),
            "ai_generated_public_indicators": len(ai_public),
            "parser_indicator_catalog": len(parser_indicator_codes),
            "ai_country_codes": len(ai_runtime["country_codes"]),
            "parser_country_catalog": len(parser_country_codes),
            "parser_intents": len(parser_intents),
            "parser_question_family_intents": len(family_intents),
        },
        "indicator_drift": {
            "parser_only_indicators": parser_only_indicators,
            "missing_from_parser_indicator_catalog": missing_in_parser,
            "forbidden_indicators_present_in_parser_catalog": forbidden_in_parser,
            "contract_vs_generated_public_diff": contract_vs_generated_diff,
        },
        "analytics_mismatch": {
            "runtime_cluster_target_years": ai_runtime["cluster_target_years"],
            "parser_cluster_target_years": parser_cluster_target_years,
            "analytics_table_indicator_mismatch": analytics_table_mismatch,
        },
        "country_mismatch": country_mismatch,
        "intent_alignment": {
            "unsupported_parser_intents_for_ai_execution": unsupported_parser_intents,
            "unsupported_question_family_intents_for_ai_execution": unsupported_question_family_intents,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit parser/catalog alignment.")
    parser.add_argument("--parser-config-dir", type=Path, default=None)
    parser.add_argument(
        "--parser-artifact-zip",
        type=Path,
        default=ROOT
        / "services"
        / "query-agent"
        / "model"
        / "government_parser_qwen3_4b_lora_artifact.zip",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
    )
    args = parser.parse_args()

    config_dir = _find_parser_config_dir(args.parser_config_dir)
    artifact_zip = _find_existing([args.parser_artifact_zip]) if args.parser_artifact_zip else None

    report = run_audit(
        parser_config_dir=config_dir,
        parser_artifact_zip=artifact_zip,
        forbidden_indicators=DEFAULT_FORBIDDEN_INDICATORS,
    )

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return

    print("Parser/Catalog Audit")
    print(f"parser_artifact_available: {report['parser_artifact_available']}")
    print(f"contract_public_indicators: {report['counts']['contract_public_indicators']}")
    print(f"ai_generated_public_indicators: {report['counts']['ai_generated_public_indicators']}")
    print(f"parser_indicator_catalog: {report['counts']['parser_indicator_catalog']}")
    print(
        "forbidden_indicators_present: "
        + ", ".join(report["indicator_drift"]["forbidden_indicators_present_in_parser_catalog"])
    )
    print(
        "parser_only_indicators: "
        + ", ".join(report["indicator_drift"]["parser_only_indicators"])
    )


if __name__ == "__main__":
    main()
