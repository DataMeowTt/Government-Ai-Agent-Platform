from __future__ import annotations

import hashlib
import json
from pathlib import Path

from config.source_registry import (
    SourceRegistryEntry,
    load_source_registry,
    normalize_registry_sources,
    normalize_source_name,
    render_source_input_required_block,
)


def load_registry(path: str | Path | None = None) -> dict[str, SourceRegistryEntry]:
    return normalize_registry_sources(load_source_registry(path))


def select_sources(
    registry: dict[str, SourceRegistryEntry],
    requested_sources: list[str] | None = None,
) -> list[SourceRegistryEntry]:
    requested = [str(item).strip() for item in (requested_sources or []) if str(item).strip()]
    if not requested or "all" in {item.lower() for item in requested}:
        return [entry for entry in registry.values() if entry.enabled]

    selected: list[SourceRegistryEntry] = []
    for source_name in requested:
        canonical_name = normalize_source_name(source_name)
        if canonical_name not in registry:
            raise KeyError(f"Unknown source requested: {source_name}")
        selected.append(registry[canonical_name])
    return selected


def compute_source_hash(
    entry: SourceRegistryEntry,
    *,
    content_hash: str | None = None,
) -> str:
    payload = {
        "source_name": entry.source_name,
        "source_type": entry.source_type,
        "enabled": entry.enabled,
        "description": entry.description,
        "license_note": entry.license_note,
        "base_url": entry.base_url,
        "api_url": entry.api_url,
        "csv_url": entry.csv_url,
        "gcs_uri": entry.gcs_uri,
        "local_path": entry.local_path,
        "output_format": entry.output_format,
        "indicator_mapping": dict(entry.indicator_mapping or {}),
        "content_hash": content_hash or "",
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_required_input_blocks(entry: SourceRegistryEntry) -> list[str]:
    return [
        render_source_input_required_block(entry.source_name, missing_field)
        for missing_field in entry.missing_inputs()
    ]


def load_previous_source_manifest(path: str | Path | None) -> dict[str, dict]:
    if not path:
        return {}
    manifest_path = Path(path).expanduser()
    if not manifest_path.exists():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_manifest = payload.get("source_manifest", payload)
    previous: dict[str, dict] = {}
    for item in source_manifest.get("sources", []):
        source_name = normalize_source_name(item["source_name"])
        previous[source_name] = {**item, "source_name": source_name}
    return previous


def decide_skip(
    *,
    entry: SourceRegistryEntry,
    source_hash: str,
    previous_sources: dict[str, dict],
    force: bool,
) -> tuple[bool, dict | None]:
    previous = previous_sources.get(entry.source_name)
    if not previous:
        return False, None
    if force:
        return False, previous
    previous_hash = previous.get("source_hash")
    if previous_hash and previous_hash == source_hash and previous.get("status") in {"ingested", "skipped"}:
        return True, previous
    return False, previous
