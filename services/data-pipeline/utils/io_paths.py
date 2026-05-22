from __future__ import annotations

from pathlib import Path


GCS_PREFIX = "gs://"
FILE_PREFIX = "file://"


def clean_uri(uri: str) -> str:
    value = str(uri or "").strip()

    if not value:
        raise ValueError("URI/path must not be empty.")

    return value.rstrip("/")


def is_gcs_uri(uri: str) -> bool:
    return clean_uri(uri).lower().startswith(GCS_PREFIX)


def is_local_uri(uri: str) -> bool:
    return not is_gcs_uri(uri)


def to_local_path(uri: str) -> Path:
    value = clean_uri(uri)

    if is_gcs_uri(value):
        raise ValueError(f"GCS URI cannot be converted to local Path: {value}")

    if value.lower().startswith(FILE_PREFIX):
        value = value[len(FILE_PREFIX):]

    return Path(value).expanduser()


def ensure_local_parent(uri: str) -> None:
    if is_gcs_uri(uri):
        return

    path = to_local_path(uri)
    parent = path.parent if path.suffix else path
    parent.mkdir(parents=True, exist_ok=True)


def dirname_uri(uri: str) -> str:
    value = clean_uri(uri)

    if is_gcs_uri(value):
        return value.rsplit("/", 1)[0]

    if value.lower().startswith(FILE_PREFIX):
        value = value[len(FILE_PREFIX):]

    normalized = value.replace("\\", "/")

    if "/" not in normalized:
        return "."

    parent = normalized.rsplit("/", 1)[0]
    return parent or "/"


def join_uri(base_uri: str, *parts: str) -> str:
    base = clean_uri(base_uri)
    clean_parts = [str(part).strip().strip("/\\") for part in parts if str(part).strip()]

    if not clean_parts:
        return base

    if is_gcs_uri(base):
        return "/".join([base, *clean_parts])

    return "/".join([base.rstrip("/\\"), *clean_parts])


def replace_filename(uri: str, filename: str) -> str:
    name = str(filename or "").strip().strip("/\\")

    if not name:
        raise ValueError("filename must not be empty.")

    return join_uri(dirname_uri(uri), name)


def output_format_from_uri(uri: str, fallback: str = "csv") -> str:
    value = clean_uri(uri).lower()

    if value.endswith(".parquet"):
        return "parquet"

    if value.endswith(".csv"):
        return "csv"

    fallback_value = str(fallback or "").strip().lower()

    if fallback_value not in {"csv", "parquet"}:
        raise ValueError(f"Invalid fallback output format: {fallback!r}")

    return fallback_value


def build_silver_output_uris(silver_output_uri: str) -> dict[str, str]:
    final_uri = clean_uri(silver_output_uri)

    return {
        "wdi": replace_filename(final_uri, "WDI_processed"),
        "macro": replace_filename(final_uri, "MACRO_processed"),
        "gmd": replace_filename(final_uri, "GMD_processed"),
        "union": final_uri,
    }