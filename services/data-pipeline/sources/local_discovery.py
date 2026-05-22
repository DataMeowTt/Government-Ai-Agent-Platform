from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any


WDI_REQUIRED_FILES = ["WDICSV.csv", "WDICountry.csv", "WDISeries.csv"]
WDI_OPTIONAL_FILES = ["WDIcountry-series.csv", "WDIfootnote.csv", "WDIseries-time.csv"]
GMD_REQUIRED_FILES = ["GMD.csv"]
GMD_OPTIONAL_FILES = ["src.txt"]
FAO_MACRO_REQUIRED_FILES = [
    "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
    "Macro-Statistics_Key_Indicators_E_AreaCodes.csv",
    "Macro-Statistics_Key_Indicators_E_Elements.csv",
    "Macro-Statistics_Key_Indicators_E_Flags.csv",
    "Macro-Statistics_Key_Indicators_E_ItemCodes.csv",
]

SOURCE_FILE_REQUIREMENTS = {
    "wdi": {
        "required": WDI_REQUIRED_FILES,
        "optional": WDI_OPTIONAL_FILES,
        "main_file": "WDICSV.csv",
    },
    "gmd": {
        "required": GMD_REQUIRED_FILES,
        "optional": GMD_OPTIONAL_FILES,
        "main_file": "GMD.csv",
    },
    "fao_macro": {
        "required": FAO_MACRO_REQUIRED_FILES,
        "optional": [],
        "main_file": "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
    },
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for read_block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(read_block)
    return digest.hexdigest()


def _csv_metadata(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return {
                "header_columns": [],
                "sample_first_data_row": None,
                "data_row_count": 0,
                "status": "invalid",
                "reason": "empty_csv",
            }

        sample_row = next(reader, None)
        row_count = 0 if sample_row is None else 1
        for _ in reader:
            row_count += 1

    return {
        "header_columns": header,
        "sample_first_data_row": sample_row,
        "data_row_count": row_count,
        "status": "present",
    }


def _relative_path(root: Path, file_path: Path) -> str:
    return file_path.relative_to(root).as_posix()


def _file_entry(root: Path, file_path: Path, *, is_required: bool, is_optional: bool) -> dict[str, Any]:
    stat = file_path.stat()
    return {
        "file_name": file_path.name,
        "relative_path": _relative_path(root, file_path),
        "relative_or_input_path": _relative_path(root, file_path),
        "absolute_path": str(file_path.resolve()),
        "sha256": _sha256_file(file_path),
        "size_bytes": int(stat.st_size),
        "status": "present",
        "is_required": bool(is_required),
        "is_optional": bool(is_optional),
    }


def _combined_sha256(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _discover_root(input_path: Path) -> Path:
    return input_path if input_path.is_dir() else input_path.parent


def _select_main_file(files: list[dict[str, Any]], main_file_name: str) -> dict[str, Any] | None:
    for entry in files:
        if entry["file_name"] == main_file_name or entry["relative_path"] == main_file_name:
            return entry
    return None


def _required_file_presence(files: list[dict[str, Any]], required_files: list[str]) -> list[str]:
    present = {entry["relative_path"] for entry in files} | {entry["file_name"] for entry in files}
    return [name for name in required_files if name not in present]


def discover_local_source(source_name: str, input_path: str | Path) -> dict[str, Any]:
    canonical_source = str(source_name).strip()
    if canonical_source not in SOURCE_FILE_REQUIREMENTS:
        raise KeyError(f"Unsupported local discovery source: {canonical_source}")

    raw_path = Path(input_path).expanduser()
    discovery = SOURCE_FILE_REQUIREMENTS[canonical_source]
    required_files = discovery["required"]
    optional_files = discovery["optional"]
    main_file_name = discovery["main_file"]

    if not raw_path.exists():
        return {
            "source_name": canonical_source,
            "input_path": str(raw_path),
            "discovery_root": str(raw_path if raw_path.is_dir() else raw_path.parent),
            "status": "missing",
            "reason": "input_path_missing",
            "file_count": 0,
            "total_bytes": 0,
            "combined_sha256": None,
            "files": [],
            "required_files": list(required_files),
            "optional_files": list(optional_files),
            "missing_required_files": list(required_files),
            "main_file": None,
            "main_file_metadata": None,
        }

    root = _discover_root(raw_path)
    files = sorted(
        (
            _file_entry(root, file_path, is_required=False, is_optional=False)
            for file_path in root.rglob("*")
            if file_path.is_file()
        ),
        key=lambda item: item["relative_path"],
    )

    present_paths = {entry["relative_path"] for entry in files}
    present_names = {entry["file_name"] for entry in files}
    missing_required_files = [
        name for name in required_files if name not in present_paths and name not in present_names
    ]
    status = "present" if not missing_required_files else "invalid"
    reason = "present" if status == "present" else "missing_required_files"

    for entry in files:
        entry["is_required"] = entry["relative_path"] in required_files or entry["file_name"] in required_files
        entry["is_optional"] = entry["relative_path"] in optional_files or entry["file_name"] in optional_files

    total_bytes = sum(int(item["size_bytes"]) for item in files)
    combined_sha256 = _combined_sha256(
        [
            f"{item['relative_path']}:{item['sha256']}:{item['size_bytes']}:{item['status']}"
            for item in files
        ]
        + [f"missing:{name}" for name in missing_required_files]
    )

    main_file = _select_main_file(files, main_file_name)
    main_file_metadata: dict[str, Any] | None = None
    if main_file is not None:
        main_file_path = Path(main_file["absolute_path"])
        try:
            metadata = _csv_metadata(main_file_path)
            if metadata.get("status") == "present":
                main_file_metadata = metadata
            else:
                status = "invalid"
                main_file_metadata = metadata
                reason = str(metadata.get("reason") or reason)
        except Exception as exc:  # pragma: no cover - defensive for malformed local files
            status = "invalid"
            main_file_metadata = {
                "header_columns": [],
                "sample_first_data_row": None,
                "data_row_count": 0,
                "status": "invalid",
                "reason": f"csv_parse_error:{exc.__class__.__name__}",
            }
            reason = str(main_file_metadata["reason"])
    else:
        status = "invalid"
        reason = "main_file_missing"

    return {
        "source_name": canonical_source,
        "input_path": str(raw_path),
        "discovery_root": str(root),
        "status": status,
        "reason": reason,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "combined_sha256": combined_sha256,
        "files": files,
        "required_files": list(required_files),
        "optional_files": list(optional_files),
        "missing_required_files": missing_required_files,
        "main_file": main_file,
        "main_file_metadata": main_file_metadata,
    }
