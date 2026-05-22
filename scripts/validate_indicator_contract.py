from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: PyYAML. Install with: pip install pyyaml"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = ROOT / "contracts" / "indicator_contract.yaml"
DEFAULT_REPORT_PATH = ROOT / "reports" / "contract_validation_report.json"


ALLOWED_GOLD_TABLES = {
    "gold_growth_dynamics",
    "gold_fiscal_monetary",
    "gold_crisis_risk",
    "gold_social_welfare",
    "gold_structural_composition",
}


TECHNICAL_CODES = {
    "decade",
    "flag_score",
    "completeness_score",
}


REQUIRED_FIELDS = [
    "public",
    "technical",
    "dimension",
    "name_vi",
    "name_en",
    "category",
    "description_vi",
    "description_en",
    "source_indicator",
    "source_priority",
    "gold_table",
    "gold_column",
    "unit",
    "value_type",
    "supports_raw",
    "supports_compare",
    "supports_ranking",
    "supports_coverage",
    "supports_trend",
    "supports_anomaly",
    "used_for_cluster",
    "imputation_policy",
    "null_policy",
    "aliases_vi",
    "aliases_en",
]


PUBLIC_REQUIRED_NON_EMPTY_FIELDS = [
    "name_vi",
    "name_en",
    "category",
    "description_vi",
    "gold_table",
    "gold_column",
    "unit",
    "value_type",
    "source_indicator",
]


BOOL_FIELDS = [
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
]


ALLOWED_IMPUTATION_POLICIES = {
    "linear_limit_2",
    "no_interpolate",
}


ALLOWED_NULL_POLICIES = {
    "preserve_null",
}


# Snapshot from current analytics-worker TABLES_INDICATORS.
# This is validation-only. Generator in the next release step must read from indicator_contract.yaml.
EXPECTED_ANALYTICS_BY_GOLD_TABLE = {
    "gold_growth_dynamics": {
        "rGDP_growth_YoY",
        "GDP_growth_YoY",
        "trend_deviation",
        "GDP_pc_growth_gap",
        "rolling_mean_5yr",
    },
    "gold_fiscal_monetary": {
        "govdebt_GDP",
        "fiscal_balance_GDP",
        "real_interest_rate",
        "inflation_gap",
        "inflation_cpi",
        "tax_revenue_pct_GDP",
    },
    "gold_crisis_risk": {
        "REER_deviation",
        "spending_efficiency",
    },
    "gold_social_welfare": {
        "poverty_headcount",
        "poverty_change_5yr",
        "hcons_growth",
        "unemployment_total",
        "youth_unemployment_gap",
    },
    "gold_structural_composition": {
        "GFCF_to_GDP",
        "GNI_to_GDP",
        "agri_va_share",
        "manuf_va_share",
        "food_bev_share_manuf",
    },
}


EXPECTED_CLUSTER_INDICATORS = {
    "agri_va_share",
    "manuf_va_share",
    "GFCF_to_GDP",
    "GNI_to_GDP",
    "poverty_headcount",
    "urban_pop_pct",
    "unemployment_total",
}


EXPECTED_ADDITIONAL_GOLD_LOCATIONS = {
    "rGDP_growth_YoY": [
        {
            "gold_table": "gold_crisis_risk",
            "gold_column": "rGDP_growth_YoY",
            "role": "support_feature",
        }
    ],
    "GDP_growth_YoY": [
        {
            "gold_table": "gold_structural_composition",
            "gold_column": "GDP_growth_YoY",
            "role": "support_feature",
        }
    ],
    "govdebt_GDP": [
        {
            "gold_table": "gold_crisis_risk",
            "gold_column": "govdebt_GDP",
            "role": "support_feature",
        }
    ],
    "fiscal_balance_GDP": [
        {
            "gold_table": "gold_crisis_risk",
            "gold_column": "fiscal_balance_GDP",
            "role": "support_feature",
        }
    ],
}


EXPECTED_COMPLETENESS_TABLES = [
    "gold_growth_dynamics",
    "gold_fiscal_monetary",
    "gold_crisis_risk",
    "gold_social_welfare",
    "gold_structural_composition",
]


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_mapping_with_unique_keys(loader: yaml.Loader, node: yaml.Node, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate YAML key detected: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping_with_unique_keys,
)


def load_yaml_unique(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing contract file: {path}")

    text = path.read_text(encoding="utf-8")
    data = yaml.load(text, Loader=UniqueKeyLoader)

    if not isinstance(data, dict):
        raise ValueError("indicator_contract.yaml must be a mapping at root level.")

    return data


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def add_warning(warnings: list[str], message: str) -> None:
    warnings.append(message)


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_basic_schema(contract: dict[str, dict[str, Any]], errors: list[str], warnings: list[str]) -> None:
    for code, entry in contract.items():
        if not isinstance(entry, dict):
            add_error(errors, f"{code}: entry must be an object.")
            continue

        for field in REQUIRED_FIELDS:
            if field not in entry:
                add_error(errors, f"{code}: missing required field `{field}`.")

        for field in BOOL_FIELDS:
            if field in entry and not isinstance(entry[field], bool):
                add_error(errors, f"{code}.{field}: must be boolean true/false.")

        if entry.get("imputation_policy") not in ALLOWED_IMPUTATION_POLICIES:
            add_error(
                errors,
                f"{code}.imputation_policy: invalid value `{entry.get('imputation_policy')}`.",
            )

        if entry.get("null_policy") not in ALLOWED_NULL_POLICIES:
            add_error(
                errors,
                f"{code}.null_policy: invalid value `{entry.get('null_policy')}`.",
            )

        for field in ["source_priority", "aliases_vi", "aliases_en"]:
            if field in entry and not isinstance(entry[field], list):
                add_error(errors, f"{code}.{field}: must be a list.")

        gold_table = entry.get("gold_table")
        if gold_table is not None and gold_table not in ALLOWED_GOLD_TABLES:
            add_error(errors, f"{code}.gold_table: unknown table `{gold_table}`.")

        gold_column = entry.get("gold_column")
        if gold_column is not None and not is_non_empty_string(gold_column):
            add_error(errors, f"{code}.gold_column: must be a non-empty string or null.")

        additional_locations = entry.get("additional_gold_locations", [])
        if additional_locations is None:
            additional_locations = []

        if not isinstance(additional_locations, list):
            add_error(errors, f"{code}.additional_gold_locations: must be a list when present.")
        else:
            for idx, location in enumerate(additional_locations):
                if not isinstance(location, dict):
                    add_error(errors, f"{code}.additional_gold_locations[{idx}]: must be an object.")
                    continue

                loc_table = location.get("gold_table")
                loc_column = location.get("gold_column")
                loc_role = location.get("role")

                if loc_table not in ALLOWED_GOLD_TABLES:
                    add_error(
                        errors,
                        f"{code}.additional_gold_locations[{idx}].gold_table: unknown table `{loc_table}`.",
                    )
                if not is_non_empty_string(loc_column):
                    add_error(
                        errors,
                        f"{code}.additional_gold_locations[{idx}].gold_column: must be non-empty string.",
                    )
                if loc_role not in {"support_feature", "duplicate_public_column"}:
                    add_error(
                        errors,
                        f"{code}.additional_gold_locations[{idx}].role: invalid role `{loc_role}`.",
                    )

        if entry.get("public") is True:
            for field in PUBLIC_REQUIRED_NON_EMPTY_FIELDS:
                if not is_non_empty_string(entry.get(field)):
                    add_error(errors, f"{code}.{field}: public indicator requires non-empty value.")

            if entry.get("technical") is True:
                add_error(errors, f"{code}: public indicator must not be technical.")

            if entry.get("dimension") is True:
                add_warning(
                    warnings,
                    f"{code}: public dimension=true is unusual. Confirm this is intentional.",
                )

            if not str(entry.get("description_en") or "").strip():
                add_warning(
                    warnings,
                    f"{code}.description_en: empty. Acceptable in V1, but should be filled later.",
                )

        if entry.get("technical") is True and entry.get("public") is True:
            add_error(errors, f"{code}: technical indicator cannot be public.")


def validate_technical_columns(contract: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for code in TECHNICAL_CODES:
        if code not in contract:
            add_error(errors, f"Missing technical contract key: {code}.")
            continue

        entry = contract[code]
        if entry.get("public") is not False:
            add_error(errors, f"{code}: technical column must have public=false.")
        if entry.get("technical") is not True:
            add_error(errors, f"{code}: technical column must have technical=true.")

    completeness = contract.get("completeness_score")
    if isinstance(completeness, dict):
        if completeness.get("gold_table") is not None:
            add_error(errors, "completeness_score.gold_table must be null.")
        tables = completeness.get("applies_to_gold_tables")
        if tables != EXPECTED_COMPLETENESS_TABLES:
            add_error(
                errors,
                "completeness_score.applies_to_gold_tables mismatch. "
                f"Expected {EXPECTED_COMPLETENESS_TABLES}, got {tables}.",
            )


def validate_analytics_flags(contract: dict[str, dict[str, Any]], errors: list[str]) -> None:
    expected_analytics_codes = set().union(*EXPECTED_ANALYTICS_BY_GOLD_TABLE.values())

    for gold_table, expected_codes in EXPECTED_ANALYTICS_BY_GOLD_TABLE.items():
        for code in expected_codes:
            if code not in contract:
                add_error(errors, f"Analytics indicator missing from contract: {code}.")
                continue

            entry = contract[code]
            if entry.get("gold_table") != gold_table:
                add_error(
                    errors,
                    f"{code}.gold_table mismatch for analytics. Expected `{gold_table}`, got `{entry.get('gold_table')}`.",
                )
            if entry.get("supports_trend") is not True:
                add_error(errors, f"{code}.supports_trend must be true.")
            if entry.get("supports_anomaly") is not True:
                add_error(errors, f"{code}.supports_anomaly must be true.")

    for code, entry in contract.items():
        if entry.get("public") is not True:
            continue

        is_expected_analytics = code in expected_analytics_codes
        has_analytics_flag = entry.get("supports_trend") is True or entry.get("supports_anomaly") is True

        if has_analytics_flag and not is_expected_analytics:
            add_error(
                errors,
                f"{code}: has analytics support flag but is not in expected analytics source map.",
            )

        if is_expected_analytics:
            continue

        if entry.get("supports_trend") is not False:
            add_error(errors, f"{code}.supports_trend must be false.")
        if entry.get("supports_anomaly") is not False:
            add_error(errors, f"{code}.supports_anomaly must be false.")


def validate_cluster_flags(contract: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for code in EXPECTED_CLUSTER_INDICATORS:
        if code not in contract:
            add_error(errors, f"Cluster indicator missing from contract: {code}.")
            continue
        if contract[code].get("used_for_cluster") is not True:
            add_error(errors, f"{code}.used_for_cluster must be true.")

    for code, entry in contract.items():
        if entry.get("used_for_cluster") is True and code not in EXPECTED_CLUSTER_INDICATORS:
            add_error(
                errors,
                f"{code}.used_for_cluster is true but code is not in expected cluster indicator list.",
            )


def normalize_locations(locations: Any) -> list[dict[str, str]]:
    if not isinstance(locations, list):
        return []

    normalized = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        normalized.append(
            {
                "gold_table": str(location.get("gold_table") or ""),
                "gold_column": str(location.get("gold_column") or ""),
                "role": str(location.get("role") or ""),
            }
        )
    return normalized


def validate_additional_locations(contract: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for code, expected_locations in EXPECTED_ADDITIONAL_GOLD_LOCATIONS.items():
        if code not in contract:
            add_error(errors, f"Missing contract key for duplicate gold location: {code}.")
            continue

        actual_locations = normalize_locations(contract[code].get("additional_gold_locations", []))

        for expected in expected_locations:
            if expected not in actual_locations:
                add_error(
                    errors,
                    f"{code}: missing additional_gold_location {expected}.",
                )


def validate_no_public_technical(contract: dict[str, dict[str, Any]], errors: list[str]) -> None:
    public_codes = [
        code
        for code, entry in contract.items()
        if isinstance(entry, dict) and entry.get("public") is True
    ]

    for technical_code in TECHNICAL_CODES:
        if technical_code in public_codes:
            add_error(errors, f"{technical_code}: technical code appears as public indicator.")


def validate_imputation_policies(contract: dict[str, dict[str, Any]], errors: list[str]) -> None:
    must_not_interpolate = {
        "poverty_headcount",
        "poverty_change_5yr",
        "SovDebtCrisis",
        "CurrencyCrisis",
        "BankingCrisis",
        "crisis_any",
        "crisis_composite",
        "decade",
        "flag_score",
        "completeness_score",
    }

    for code in must_not_interpolate:
        if code not in contract:
            add_error(errors, f"Missing imputation policy target: {code}.")
            continue
        if contract[code].get("imputation_policy") != "no_interpolate":
            add_error(errors, f"{code}.imputation_policy must be no_interpolate.")


def build_summary(contract: dict[str, dict[str, Any]]) -> dict[str, Any]:
    public_codes = [
        code
        for code, entry in contract.items()
        if isinstance(entry, dict) and entry.get("public") is True
    ]
    analytics_codes = [
        code
        for code, entry in contract.items()
        if isinstance(entry, dict)
        and entry.get("public") is True
        and (entry.get("supports_trend") is True or entry.get("supports_anomaly") is True)
    ]
    cluster_codes = [
        code
        for code, entry in contract.items()
        if isinstance(entry, dict) and entry.get("used_for_cluster") is True
    ]

    return {
        "total_entries": len(contract),
        "public_indicators": len(public_codes),
        "technical_entries": len([code for code in contract if code in TECHNICAL_CODES]),
        "analytics_indicators": len(analytics_codes),
        "cluster_indicators": len(cluster_codes),
        "public_codes_sample": sorted(public_codes)[:10],
        "analytics_codes": sorted(analytics_codes),
        "cluster_codes": sorted(cluster_codes),
    }


def validate_contract(contract_path: Path, report_path: Path, strict_description_en: bool) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        contract = load_yaml_unique(contract_path)
    except Exception as exc:
        report = {
            "status": "failed",
            "contract_path": str(contract_path),
            "errors": [str(exc)],
            "warnings": [],
        }
        write_report(report_path, report)
        print_report(report)
        return 1

    validate_basic_schema(contract, errors, warnings)
    validate_technical_columns(contract, errors)
    validate_analytics_flags(contract, errors)
    validate_cluster_flags(contract, errors)
    validate_additional_locations(contract, errors)
    validate_no_public_technical(contract, errors)
    validate_imputation_policies(contract, errors)

    if strict_description_en:
        for code, entry in contract.items():
            if entry.get("public") is True and not str(entry.get("description_en") or "").strip():
                errors.append(f"{code}.description_en: empty while --strict-description-en is enabled.")

    status = "passed" if not errors else "failed"
    report = {
        "status": status,
        "contract_path": str(contract_path),
        "summary": build_summary(contract),
        "errors": errors,
        "warnings": warnings,
    }

    write_report(report_path, report)
    print_report(report)

    return 0 if not errors else 1


def write_report(report_path: Path, report: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_report(report: dict[str, Any]) -> None:
    print("")
    print("=== Indicator Contract Validation ===")
    print(f"Status: {report.get('status')}")
    print("")

    summary = report.get("summary") or {}
    if summary:
        print("Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        print("")

    warnings = report.get("warnings") or []
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
        print("")

    errors = report.get("errors") or []
    if errors:
        print(f"Errors ({len(errors)}):")
        for error in errors:
            print(f"  - {error}")
        print("")
    else:
        print("No validation errors.")
        print("")

    print(f"Report written to: {DEFAULT_REPORT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate contracts/indicator_contract.yaml")
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_CONTRACT_PATH),
        help="Path to indicator_contract.yaml",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to validation report JSON",
    )
    parser.add_argument(
        "--strict-description-en",
        action="store_true",
        help="Fail when public indicators have empty description_en.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = validate_contract(
        contract_path=Path(args.contract),
        report_path=Path(args.report),
        strict_description_en=bool(args.strict_description_en),
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()