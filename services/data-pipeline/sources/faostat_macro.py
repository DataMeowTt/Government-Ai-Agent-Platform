from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

from sources.official_acquisition import (
    AcquisitionError,
    collect_file_metadata,
    compute_combined_fingerprint,
    read_csv_header_and_count,
    schema_signature,
    sha256_bytes,
)

FAO_CATALOG_URL = "https://bulks-faostat.fao.org/production/datasets_E.json"
FAO_REQUIRED_FILES = [
    "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
    "Macro-Statistics_Key_Indicators_E_AreaCodes.csv",
    "Macro-Statistics_Key_Indicators_E_Elements.csv",
    "Macro-Statistics_Key_Indicators_E_Flags.csv",
    "Macro-Statistics_Key_Indicators_E_ItemCodes.csv",
]
FAO_RUNTIME_DIR = "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)"


class FaoNetworkBlockedError(AcquisitionError):
    pass


def default_fetch_catalog() -> list[dict]:
    try:
        with urlopen(FAO_CATALOG_URL, timeout=60) as response:  # nosec B310
            raw_payload = response.read()
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT catalog fetch failed: {exc}") from exc
    try:
        decoded = json.loads(raw_payload.decode("utf-8"))
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT catalog parse failed: {exc}") from exc
    if isinstance(decoded, list):
        return [item for item in decoded if isinstance(item, dict)]
    if isinstance(decoded, dict):
        datasets = decoded.get("Datasets")
        if isinstance(datasets, dict):
            entries = datasets.get("Dataset")
            if isinstance(entries, list):
                return [item for item in entries if isinstance(item, dict)]
            if isinstance(entries, dict):
                return [entries]
        if isinstance(datasets, list):
            return [item for item in datasets if isinstance(item, dict)]
        if isinstance(decoded.get("Dataset"), list):
            return [item for item in decoded["Dataset"] if isinstance(item, dict)]
    raise AcquisitionError("FAOSTAT catalog format is unsupported for dataset extraction.")


def default_download_bytes(url: str) -> bytes:
    try:
        with urlopen(url, timeout=60) as response:  # nosec B310
            return response.read()
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT archive download failed: {exc}") from exc


def _select_mk_dataset(catalog_entries: list[dict]) -> dict:
    matches = [entry for entry in catalog_entries if str(entry.get("DatasetCode", "")).strip() == "MK"]
    if len(matches) != 1:
        raise AcquisitionError(f"FAOSTAT catalog MK selection invalid, matches={len(matches)}")
    chosen = matches[0]
    dataset_name = str(chosen.get("DatasetName", "")).lower()
    if "macro" not in dataset_name:
        raise AcquisitionError("FAOSTAT MK dataset name does not look like Macro Indicators.")
    return chosen


def materialize_fao_macro(
    *,
    runtime_raw_dir: Path,
    allow_network: bool,
    fetch_catalog: Callable[[], list[dict]] | None = None,
    download_bytes: Callable[[str], bytes] | None = None,
) -> dict:
    if not allow_network:
        raise FaoNetworkBlockedError("Network not allowed for FAOSTAT acquisition. Use --allow-network or test fixtures.")

    catalog_fn = fetch_catalog or default_fetch_catalog
    download_fn = download_bytes or default_download_bytes

    try:
        catalog_entries = catalog_fn()
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT catalog fetch failed: {exc}") from exc
    try:
        chosen = _select_mk_dataset(catalog_entries)
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT catalog selection failed: {exc}") from exc
    file_location = str(chosen.get("FileLocation", "")).strip()
    if not file_location:
        raise AcquisitionError("FAOSTAT MK dataset missing FileLocation in catalog.")

    try:
        payload = download_fn(file_location)
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT archive download failed: {exc}") from exc
    try:
        is_zip = zipfile.is_zipfile(io.BytesIO(payload))
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT archive validation failed: {exc}") from exc
    if not is_zip:
        raise AcquisitionError("FAOSTAT MK payload is not a valid ZIP archive.")

    runtime_dir = runtime_raw_dir / FAO_RUNTIME_DIR
    runtime_dir.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.namelist() if not member.endswith("/")]
            basename_index = {Path(member).name: member for member in members}
            for file_name in FAO_REQUIRED_FILES:
                source_name = basename_index.get(file_name)
                if not source_name:
                    continue
                target_path = runtime_dir / file_name
                target_path.write_bytes(archive.read(source_name))
                mapping[source_name] = file_name
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"FAOSTAT archive extraction failed: {exc}") from exc

    present_files = sorted([p.name for p in runtime_dir.glob("*.csv") if p.is_file()])
    missing_files = [name for name in FAO_REQUIRED_FILES if name not in present_files]
    if missing_files:
        raise AcquisitionError(f"FAOSTAT MK required files missing after materialization: {missing_files}")

    main_file = runtime_dir / FAO_REQUIRED_FILES[0]
    header, row_count = read_csv_header_and_count(main_file)
    if row_count < 1:
        raise AcquisitionError("FAOSTAT MK main CSV contains no data rows.")

    file_hashes, file_sizes = collect_file_metadata(runtime_dir, present_files)
    entry = {
        "source_name": "fao_macro",
        "acquisition_method": "faostat_catalog_mk_zip",
        "official_reference": FAO_CATALOG_URL,
        "upstream_dataset_code": str(chosen.get("DatasetCode")),
        "upstream_dataset_name": chosen.get("DatasetName"),
        "upstream_version": chosen.get("CompressionFormat") or None,
        "upstream_update_date": chosen.get("DateUpdate"),
        "upstream_file_location_or_package_identifier": file_location,
        "runtime_materialized_path": str(runtime_dir),
        "upstream_to_runtime_filename_mapping": mapping,
        "required_files": list(FAO_REQUIRED_FILES),
        "present_files": present_files,
        "missing_files": missing_files,
        "file_hashes": file_hashes,
        "file_sizes": file_sizes,
        "main_file_row_count": row_count,
        "main_file_schema_signature": schema_signature(header),
        "license_note": "FAOSTAT/FAO data with attribution requirements.",
        "validation_status": "valid",
        "error_message": None,
        "catalog_metadata": {
            "DatasetCode": chosen.get("DatasetCode"),
            "DatasetName": chosen.get("DatasetName"),
            "DateUpdate": chosen.get("DateUpdate"),
            "FileLocation": chosen.get("FileLocation"),
            "FileRows": chosen.get("FileRows"),
            "CompressionFormat": chosen.get("CompressionFormat"),
            "FileType": chosen.get("FileType"),
        },
        "archive_sha256": sha256_bytes(payload),
    }
    entry["combined_fingerprint"] = compute_combined_fingerprint(entry)
    return entry
