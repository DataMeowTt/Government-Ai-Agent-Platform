from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Callable

import requests

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
WDI_BULK_DOWNLOAD_URL = "https://databank.worldbank.org/data/download/WDI_CSV.zip"
WDI_ACCESS_PRIMER_URL = "https://datatopics.worldbank.org/world-development-indicators/"


class WdiNetworkBlockedError(AcquisitionError):
    pass


def default_wdi_archive_resolver() -> str:
    # Stable public bulk endpoint referenced by World Bank's WDI topics page.
    return WDI_BULK_DOWNLOAD_URL


def default_download_bytes(url: str) -> bytes:
    # The WDI bulk file is large and occasionally terminates early.
    # Use ranged retries with fresh sessions to resume safely.
    buffer = bytearray()
    downloaded = 0
    total_size: int | None = None
    last_error: Exception | None = None

    for _ in range(120):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        try:
            # Prime access path used by World Bank before requesting the archive.
            session.get(WDI_ACCESS_PRIMER_URL, timeout=60)
            headers = {"Accept-Encoding": "identity", "Range": f"bytes={downloaded}-"}
            with session.get(url, timeout=120, stream=True, allow_redirects=True, headers=headers) as response:
                if response.status_code == 403:
                    continue
                response.raise_for_status()

                content_range = response.headers.get("Content-Range", "")
                if "/" in content_range:
                    try:
                        total_size = int(content_range.split("/")[-1])
                    except ValueError:
                        total_size = total_size
                elif total_size is None:
                    content_length = response.headers.get("Content-Length")
                    if content_length and content_length.isdigit():
                        total_size = int(content_length)

                if downloaded > 0 and response.status_code == 200:
                    buffer = bytearray()
                    downloaded = 0

                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    downloaded += len(chunk)

                if total_size is not None and downloaded >= total_size:
                    return bytes(buffer)
                if total_size is None and downloaded > 0:
                    return bytes(buffer)
                last_error = RuntimeError("WDI download yielded no progress.")
        except Exception as exc:
            last_error = exc

    raise AcquisitionError(
        f"WDI download failed after resumable retries: downloaded={downloaded} total={total_size} error={last_error}"
    ) from last_error


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
