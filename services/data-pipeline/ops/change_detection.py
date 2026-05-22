from __future__ import annotations

import json
from pathlib import Path


def load_previous_source_manifest(path: str | Path) -> tuple[dict | None, bool]:
    manifest_path = Path(path).expanduser()
    if not manifest_path.exists():
        return None, True

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "source_manifest" in payload:
        payload = payload["source_manifest"]
    return payload, False


def _file_identity(source_name: str, file_entry: dict) -> str:
    return f"{source_name}:{file_entry.get('relative_or_input_path')}"


def manifest_file_index(source_manifest: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for source in sorted(source_manifest.get("sources", []), key=lambda item: item["source_name"]):
        source_name = source["source_name"]
        for file_entry in sorted(
            source.get("files", []),
            key=lambda item: str(item.get("relative_or_input_path") or ""),
        ):
            identity = _file_identity(source_name, file_entry)
            index[identity] = {
                "source_name": source_name,
                "relative_or_input_path": file_entry.get("relative_or_input_path"),
                "sha256": file_entry.get("sha256"),
                "size_bytes": file_entry.get("size_bytes"),
                "status": file_entry.get("status"),
            }
    return index


def decide_source_change(
    *,
    current_manifest: dict,
    previous_manifest: dict | None = None,
    previous_manifest_missing: bool = False,
    force: bool = False,
) -> dict:
    current_index = manifest_file_index(current_manifest)
    current_missing = sorted(
        identity for identity, item in current_index.items() if item.get("status") == "missing"
    )

    if previous_manifest_missing or previous_manifest is None:
        return {
            "source_changed": True,
            "should_run": True,
            "force": bool(force),
            "reason": "no_previous_manifest",
            "changed_sources": sorted({item["source_name"] for item in current_index.values()}),
            "changed_files": sorted(current_index),
            "missing_current_files": current_missing,
            "missing_previous_manifest": True,
        }

    previous_index = manifest_file_index(previous_manifest)
    changed_files: list[str] = []
    for identity in sorted(set(current_index) | set(previous_index)):
        if current_index.get(identity) != previous_index.get(identity):
            changed_files.append(identity)

    changed_sources = sorted(
        {
            identity.split(":", 1)[0]
            for identity in changed_files
        }
    )

    if current_missing:
        reason = "current_source_missing"
        should_run = True
        source_changed = True
    elif changed_files:
        reason = "source_changed"
        should_run = True
        source_changed = True
    elif force:
        reason = "force"
        should_run = True
        source_changed = False
    else:
        reason = "unchanged"
        should_run = False
        source_changed = False

    return {
        "source_changed": source_changed,
        "should_run": should_run,
        "force": bool(force),
        "reason": reason,
        "changed_sources": changed_sources,
        "changed_files": changed_files,
        "missing_current_files": current_missing,
        "missing_previous_manifest": False,
    }

