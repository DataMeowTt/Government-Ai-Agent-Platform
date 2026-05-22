from __future__ import annotations

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
CONTRACT_PATH = ROOT / "contracts" / "indicator_contract.yaml"
AI_SERVICE_PATH = ROOT / "services" / "ai-agent-service"

sys.path.insert(0, str(AI_SERVICE_PATH))

from app.catalog.canonical_indicator_catalog import list_indicators  # noqa: E402


HEADER = """# Unified indicator contract for Government AI Agent Platform
# Root keys are indicator/technical-column codes.
# Runtime services should not read this YAML directly; generated artifacts will be created in the next release step.
#
# NOTE:
# imputation_policy is the desired contract behavior.
# Current pipeline must be aligned in the next pipeline/audit release step so poverty_headcount,
# poverty_change_5yr and crisis flags are not interpolated.
#
# MIGRATION NOTE:
# This patch script temporarily imports the old AI catalog only to migrate metadata into this contract.
# After this release step, generators must read from indicator_contract.yaml, not from the old AI catalog.

"""


FIELD_ORDER = [
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
    "applies_to_gold_tables",
    "additional_gold_locations",
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


MANUAL_METADATA: dict[str, dict[str, str]] = {
    "completeness_score": {
        "name_vi": "Điểm đầy đủ dữ liệu",
        "name_en": "Data Completeness Score",
        "category": "quality",
        "description_vi": "Điểm kỹ thuật đo tỷ lệ trường dữ liệu không null trong một dòng Gold.",
        "description_en": "Technical score measuring the share of non-null data fields in a Gold row.",
    },
}


def load_contract() -> dict[str, dict[str, Any]]:
    if not CONTRACT_PATH.exists():
        raise FileNotFoundError(f"Missing contract file: {CONTRACT_PATH}")

    with CONTRACT_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("indicator_contract.yaml must be a YAML mapping at root level.")

    return data


def load_ai_metadata() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    for item in list_indicators():
        result[item.code] = {
            "name_vi": item.name_vi,
            "name_en": item.name_en,
            "category": item.category,
            "description_vi": item.description_vi or "",
            "description_en": item.description_en or "",
        }

    result.update(MANUAL_METADATA)
    return result


def reorder_entry(entry: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}

    for key in FIELD_ORDER:
        if key in entry:
            ordered[key] = entry[key]

    for key, value in entry.items():
        if key not in ordered:
            ordered[key] = value

    return ordered


def patch_contract() -> None:
    contract = load_contract()
    metadata_by_code = load_ai_metadata()

    missing_metadata: list[str] = []
    empty_required_public_metadata: list[str] = []
    patched_count = 0

    for code, entry in contract.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Contract entry must be an object: {code}")

        metadata = metadata_by_code.get(code)
        if not metadata:
            missing_metadata.append(code)
            continue

        for field_name, field_value in metadata.items():
            entry[field_name] = field_value

        if entry.get("public") is True:
            for required_field in ("name_vi", "name_en", "category", "description_vi"):
                if not str(entry.get(required_field) or "").strip():
                    empty_required_public_metadata.append(f"{code}.{required_field}")

        contract[code] = reorder_entry(entry)
        patched_count += 1

    if missing_metadata:
        raise ValueError(
            "Missing metadata for contract keys: "
            + ", ".join(sorted(missing_metadata))
        )

    if empty_required_public_metadata:
        raise ValueError(
            "Empty required public metadata fields: "
            + ", ".join(sorted(empty_required_public_metadata))
        )

    empty_description_en = [
        code
        for code, entry in contract.items()
        if entry.get("public") is True and not str(entry.get("description_en") or "").strip()
    ]

    if empty_description_en:
        print(
            "WARNING: Public indicators with empty description_en: "
            + ", ".join(sorted(empty_description_en))
        )
        print(
            "This is acceptable in V1 only if English descriptions are filled later."
        )

    output = yaml.safe_dump(
        contract,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )

    CONTRACT_PATH.write_text(HEADER + output, encoding="utf-8")

    print(f"Patched metadata for {patched_count} contract entries.")
    print(f"Updated: {CONTRACT_PATH}")


if __name__ == "__main__":
    patch_contract()
