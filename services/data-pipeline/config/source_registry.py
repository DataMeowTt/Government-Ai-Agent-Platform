from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from config.settings import settings

SUPPORTED_SOURCE_TYPES = {"api", "csv_url", "gcs_uri", "local_path"}
SUPPORTED_OUTPUT_FORMATS = {"csv", "parquet", "json"}
SOURCE_NAME_ALIASES = {"macro": "fao_macro"}

_FIELD_LABELS = {
    "api_url": "api_url",
    "csv_url": "csv_url",
    "gcs_uri": "gcs_uri",
    "local_path": "local_path",
    "license_note": "license note",
    "indicator_mapping": "indicator_mapping",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def normalize_source_name(source_name: str) -> str:
    clean = _clean_text(source_name)
    return SOURCE_NAME_ALIASES.get(clean, clean)


@dataclass(frozen=True)
class SourceRegistryEntry:
    source_name: str
    source_type: str
    enabled: bool
    description: str
    license_note: str | None = None
    base_url: str | None = None
    api_url: str | None = None
    csv_url: str | None = None
    gcs_uri: str | None = None
    local_path: str | None = None
    indicator_mapping: Mapping[str, str] | None = None
    output_format: str = "csv"
    raw: dict[str, Any] = field(default_factory=dict)

    def missing_inputs(self) -> list[str]:
        missing: list[str] = []

        if _clean_text(self.license_note) == "":
            missing.append(_FIELD_LABELS["license_note"])

        source_type = _clean_text(self.source_type).lower()
        if source_type not in SUPPORTED_SOURCE_TYPES:
            missing.append("source_type")
            return _unique_preserve_order(missing)

        if source_type == "api":
            if _clean_text(self.api_url) == "":
                missing.append(_FIELD_LABELS["api_url"])
            if not self.indicator_mapping:
                missing.append(_FIELD_LABELS["indicator_mapping"])
        elif source_type == "csv_url":
            if _clean_text(self.csv_url) == "":
                missing.append(_FIELD_LABELS["csv_url"])
        elif source_type == "gcs_uri":
            if _clean_text(self.gcs_uri) == "":
                missing.append(_FIELD_LABELS["gcs_uri"])
        elif source_type == "local_path":
            if _clean_text(self.local_path) == "":
                missing.append(_FIELD_LABELS["local_path"])

        return _unique_preserve_order(missing)

    def required_input_fields(self) -> list[str]:
        source_type = _clean_text(self.source_type).lower()
        if source_type == "api":
            return ["api_url", "indicator_mapping"]
        if source_type == "csv_url":
            return ["csv_url"]
        if source_type == "gcs_uri":
            return ["gcs_uri"]
        if source_type == "local_path":
            return ["local_path"]
        return []

    def fingerprint_components(self) -> list[str]:
        indicator_items: list[str] = []
        if self.indicator_mapping:
            indicator_items = [
                f"{key}={value}"
                for key, value in sorted(self.indicator_mapping.items())
            ]

        return [
            f"source_name={_clean_text(self.source_name)}",
            f"source_type={_clean_text(self.source_type).lower()}",
            f"enabled={bool(self.enabled)}",
            f"description={_clean_text(self.description)}",
            f"license_note={_clean_text(self.license_note)}",
            f"base_url={_clean_text(self.base_url)}",
            f"api_url={_clean_text(self.api_url)}",
            f"csv_url={_clean_text(self.csv_url)}",
            f"gcs_uri={_clean_text(self.gcs_uri)}",
            f"local_path={_clean_text(self.local_path)}",
            f"output_format={_clean_text(self.output_format).lower()}",
            f"indicator_mapping={'|'.join(indicator_items)}",
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_name": _clean_text(self.source_name),
            "source_type": _clean_text(self.source_type).lower(),
            "enabled": bool(self.enabled),
            "description": _clean_text(self.description),
            "license_note": self.license_note,
            "base_url": self.base_url,
            "api_url": self.api_url,
            "csv_url": self.csv_url,
            "gcs_uri": self.gcs_uri,
            "local_path": self.local_path,
            "indicator_mapping": dict(self.indicator_mapping or {}),
            "output_format": _clean_text(self.output_format).lower() or "csv",
        }


def _coerce_entry(raw: dict[str, Any]) -> SourceRegistryEntry:
    source_name = _clean_text(raw.get("source_name"))
    source_type = _clean_text(raw.get("source_type")).lower()
    enabled = bool(raw.get("enabled", True))
    description = _clean_text(raw.get("description"))
    output_format = _clean_text(raw.get("output_format") or "csv").lower()
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(
            f"Invalid output_format={output_format!r} for source {source_name!r}. "
            f"Expected one of: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )

    indicator_mapping = raw.get("indicator_mapping")
    if indicator_mapping is not None and not isinstance(indicator_mapping, dict):
        raise ValueError(
            f"indicator_mapping for source {source_name!r} must be a mapping if provided."
        )

    extra = {
        key: value
        for key, value in raw.items()
        if key not in {
            "source_name",
            "source_type",
            "enabled",
            "description",
            "license_note",
            "base_url",
            "api_url",
            "csv_url",
            "gcs_uri",
            "local_path",
            "indicator_mapping",
            "output_format",
        }
    }

    return SourceRegistryEntry(
        source_name=source_name,
        source_type=source_type,
        enabled=enabled,
        description=description,
        license_note=raw.get("license_note"),
        base_url=raw.get("base_url"),
        api_url=raw.get("api_url"),
        csv_url=raw.get("csv_url"),
        gcs_uri=raw.get("gcs_uri"),
        local_path=raw.get("local_path"),
        indicator_mapping=indicator_mapping,
        output_format=output_format,
        raw=extra,
    )


def load_source_registry(path: str | Path | None = None) -> dict[str, SourceRegistryEntry]:
    registry_path = Path(path or settings.source_registry_path).expanduser()
    if not registry_path.exists():
        raise FileNotFoundError(f"Source registry not found: {registry_path}")

    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("source_registry.yaml must contain a top-level 'sources' list.")

    registry: dict[str, SourceRegistryEntry] = {}
    for raw in sources:
        if not isinstance(raw, dict):
            raise ValueError("Each source registry entry must be a mapping.")
        entry = _coerce_entry(raw)
        if not entry.source_name:
            raise ValueError("source_name must not be empty in source registry.")
        if entry.source_name in registry:
            raise ValueError(f"Duplicate source_name in registry: {entry.source_name}")
        registry[entry.source_name] = entry

    return registry


def normalize_registry_sources(registry: dict[str, SourceRegistryEntry]) -> dict[str, SourceRegistryEntry]:
    normalized: dict[str, SourceRegistryEntry] = {}
    for source_name, entry in registry.items():
        canonical_name = normalize_source_name(source_name)
        if canonical_name in normalized and canonical_name != source_name:
            continue
        if canonical_name == entry.source_name:
            normalized[canonical_name] = entry
            continue
        normalized[canonical_name] = SourceRegistryEntry(
            source_name=canonical_name,
            source_type=entry.source_type,
            enabled=entry.enabled,
            description=entry.description,
            license_note=entry.license_note,
            base_url=entry.base_url,
            api_url=entry.api_url,
            csv_url=entry.csv_url,
            gcs_uri=entry.gcs_uri,
            local_path=entry.local_path,
            indicator_mapping=entry.indicator_mapping,
            output_format=entry.output_format,
            raw=dict(entry.raw),
        )
    return normalized


def source_input_required_question(source_name: str, missing_field: str) -> str:
    clean_source = _clean_text(source_name)
    clean_field = _clean_text(missing_field)
    if clean_field == "api_url":
        return f"Please provide the exact API endpoint URL for source {clean_source}."
    if clean_field == "csv_url":
        return f"Please provide the exact CSV URL for source {clean_source}."
    if clean_field == "gcs_uri":
        return f"Please provide the exact GCS URI for source {clean_source}."
    if clean_field == "local_path":
        return f"Please provide the exact local file path for source {clean_source}."
    if clean_field == "license note":
        return f"Please provide the license/usage note for source {clean_source}."
    if clean_field == "indicator_mapping":
        return f"Please provide the exact indicator mapping for source {clean_source}."
    return f"Please provide the missing {clean_field} for source {clean_source}."


def render_source_input_required_block(source_name: str, missing_field: str) -> str:
    return "\n".join(
        [
            "SOURCE INPUT REQUIRED:",
            f"- source_name: {source_name}",
            f"- missing field: {missing_field}",
            f"- exact question for user: {source_input_required_question(source_name, missing_field)}",
        ]
    )
