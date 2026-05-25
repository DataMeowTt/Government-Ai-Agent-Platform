from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from sources.official_acquisition import (
    AcquisitionError,
    collect_file_metadata,
    compute_combined_fingerprint,
    read_csv_header_and_count,
    schema_signature,
    utc_now_iso,
)

GMD_OFFICIAL_REFERENCE = "https://www.globalmacrodata.com/data.html"


def _import_gmd_callable() -> Callable[..., Any]:
    try:
        from global_macro_data import gmd as gmd_callable  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise AcquisitionError(f"Global Macro Database package unavailable: {exc}") from exc
    return gmd_callable


def materialize_gmd(
    *,
    runtime_raw_dir: Path,
    allow_network: bool,
    gmd_callable: Callable[..., Any] | None = None,
    retrieved_version: str | None = None,
) -> dict:
    if not allow_network:
        raise AcquisitionError("Network/package acquisition not allowed for GMD. Use --allow-network or test fixtures.")

    try:
        loader = gmd_callable or _import_gmd_callable()
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"GMD package loader initialization failed: {exc}") from exc
    try:
        dataframe = loader(show_preview=False)
    except TypeError as exc:
        if "Unexpected keyword argument" not in str(exc):
            raise AcquisitionError(f"GMD full dataset acquisition failed: {exc}") from exc
        try:
            dataframe = loader()
        except Exception as fallback_exc:
            raise AcquisitionError(f"GMD full dataset acquisition failed: {fallback_exc}") from fallback_exc
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"GMD full dataset acquisition failed: {exc}") from exc
    if dataframe is None or getattr(dataframe, "empty", True):
        raise AcquisitionError("Global Macro Database returned empty full dataset.")

    runtime_dir = runtime_raw_dir / "gmd"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    csv_path = runtime_dir / "GMD.csv"
    dataframe.to_csv(csv_path, index=False)
    header, row_count = read_csv_header_and_count(csv_path)
    if row_count < 1:
        raise AcquisitionError("GMD.csv has no data rows after materialization.")

    version_text = retrieved_version or "unavailable_at_runtime"
    src_path = runtime_dir / "src.txt"
    src_path.write_text(
        "\n".join(
            [
                "upstream_source_name: Global Macro Database",
                f"resolved_or_retrieved_version: {version_text}",
                "acquisition_method: python_package_global_macro_data_gmd_show_preview_false",
                "citation_license_note: Global Macro Database (CC BY-NC-SA 4.0, non-commercial use with attribution).",
                f"retrieval_timestamp_utc: {utc_now_iso()}",
                f"official_reference: {GMD_OFFICIAL_REFERENCE}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    present_files = ["GMD.csv", "src.txt"]
    file_hashes, file_sizes = collect_file_metadata(runtime_dir, present_files)

    entry = {
        "source_name": "gmd",
        "acquisition_method": "global_macro_data_package_full_dataset",
        "official_reference": GMD_OFFICIAL_REFERENCE,
        "upstream_dataset_code": "GMD",
        "upstream_dataset_name": "Global Macro Database",
        "upstream_version": version_text,
        "upstream_update_date": None,
        "upstream_file_location_or_package_identifier": "global_macro_data.gmd(show_preview=False)",
        "runtime_materialized_path": str(runtime_dir),
        "upstream_to_runtime_filename_mapping": {
            "global_macro_data.gmd(show_preview=False)": "GMD.csv",
            "generated_provenance": "src.txt",
        },
        "required_files": ["GMD.csv", "src.txt"],
        "present_files": present_files,
        "missing_files": [],
        "file_hashes": file_hashes,
        "file_sizes": file_sizes,
        "main_file_row_count": row_count,
        "main_file_schema_signature": schema_signature(header),
        "license_note": "CC BY-NC-SA 4.0, non-commercial use with attribution.",
        "validation_status": "valid",
        "error_message": None,
    }
    entry["combined_fingerprint"] = compute_combined_fingerprint(entry)
    return entry
