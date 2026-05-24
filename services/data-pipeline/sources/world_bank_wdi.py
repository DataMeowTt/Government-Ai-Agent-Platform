from __future__ import annotations

import io
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

WDI_REQUIRED_FILES = ["WDICSV.csv", "WDICountry.csv", "WDISeries.csv"]
WDI_OPTIONAL_FILES = ["WDIcountry-series.csv", "WDIseries-time.csv", "WDIfootnote.csv"]
WDI_OFFICIAL_REFERENCE = "https://wdi.worldbank.org/"
WDI_DATASET_NAME = "World Development Indicators"


class WdiNetworkBlockedError(AcquisitionError):
    pass


def default_wdi_archive_resolver() -> str:
    raise AcquisitionError("WDI archive resolver is not configured for live resolution.")


def default_download_bytes(url: str) -> bytes:
    try:
        with urlopen(url, timeout=60) as response:  # nosec B310
            return response.read()
    except Exception as exc:
        raise AcquisitionError(f"WDI download failed: {exc}") from exc


def _is_html_like(payload: bytes) -> bool:
    snippet = payload[:256].strip().lower()
    return snippet.startswith(b"<") or b"<html" in snippet


def materialize_wdi(
    *,
    runtime_raw_dir: Path,
    allow_network: bool,
    resolve_archive_url: Callable[[], str] | None = None,
    download_bytes: Callable[[str], bytes] | None = None,
) -> dict:
    if not allow_network:
        raise WdiNetworkBlockedError("Network not allowed for WDI acquisition. Use --allow-network or test fixtures.")

    resolver = resolve_archive_url or default_wdi_archive_resolver
    downloader = download_bytes or default_download_bytes

    try:
        archive_url = resolver()
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"WDI archive resolution failed: {exc}") from exc

    try:
        payload = downloader(archive_url)
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"WDI download failed: {exc}") from exc
    if not payload:
        raise AcquisitionError("WDI archive payload is empty.")
    if _is_html_like(payload):
        raise AcquisitionError("WDI archive payload appears to be HTML/error content.")

    try:
        is_zip = zipfile.is_zipfile(io.BytesIO(payload))
    except Exception as exc:
        raise AcquisitionError(f"WDI archive validation failed: {exc}") from exc
    if not is_zip:
        raise AcquisitionError("WDI payload is not a valid ZIP archive.")

    runtime_dir = runtime_raw_dir / "worldBank"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    name_map: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.namelist() if not member.endswith("/")]
            basename_index = {Path(member).name: member for member in members}

            for file_name in WDI_REQUIRED_FILES + WDI_OPTIONAL_FILES:
                source_name = basename_index.get(file_name)
                if not source_name:
                    continue
                target_path = runtime_dir / file_name
                target_path.write_bytes(archive.read(source_name))
                name_map[source_name] = file_name
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"WDI archive extraction failed: {exc}") from exc

    present_files = sorted([p.name for p in runtime_dir.glob("*.csv") if p.is_file()])
    missing_files = [name for name in WDI_REQUIRED_FILES if name not in present_files]
    if missing_files:
        raise AcquisitionError(f"WDI required files missing after materialization: {missing_files}")

    main_file = runtime_dir / "WDICSV.csv"
    header, row_count = read_csv_header_and_count(main_file)
    if row_count < 1:
        raise AcquisitionError("WDI main CSV contains no data rows.")

    file_hashes, file_sizes = collect_file_metadata(runtime_dir, present_files)
    entry = {
        "source_name": "wdi",
        "acquisition_method": "wdi_bulk_archive_zip",
        "official_reference": WDI_OFFICIAL_REFERENCE,
        "upstream_dataset_code": "WDI",
        "upstream_dataset_name": WDI_DATASET_NAME,
        "upstream_version": None,
        "upstream_update_date": None,
        "upstream_file_location_or_package_identifier": archive_url,
        "runtime_materialized_path": str(runtime_dir),
        "upstream_to_runtime_filename_mapping": name_map,
        "required_files": list(WDI_REQUIRED_FILES),
        "present_files": present_files,
        "missing_files": missing_files,
        "file_hashes": file_hashes,
        "file_sizes": file_sizes,
        "main_file_row_count": row_count,
        "main_file_schema_signature": schema_signature(header),
        "license_note": "World Bank WDI open data; verify indicator-specific metadata for license terms.",
        "validation_status": "valid",
        "error_message": None,
        "archive_sha256": sha256_bytes(payload),
    }
    entry["combined_fingerprint"] = compute_combined_fingerprint(entry)
    return entry
