from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(str(uri or "").strip())
    if parsed.scheme != "gs":
        raise ValueError(f"GCS URI must use gs:// scheme: {uri!r}")
    bucket = (parsed.netloc or "").strip()
    object_path = (parsed.path or "").lstrip("/")
    if not bucket or not object_path:
        raise ValueError(f"GCS URI must include bucket and object path: {uri!r}")
    return bucket, object_path


def _build_storage_client(client_factory: Callable[[], Any] | None = None) -> Any:
    if client_factory is not None:
        return client_factory()
    from google.cloud import storage

    return storage.Client()


def upload_file_to_gcs_uri(
    *,
    local_path: str | Path,
    target_gcs_uri: str,
    content_type: str | None = None,
    if_generation_match: int | None = None,
    client_factory: Callable[[], Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    file_path = Path(local_path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Local upload file not found: {file_path}")

    bucket_name, object_path = parse_gcs_uri(target_gcs_uri)
    active_client = client or _build_storage_client(client_factory)
    bucket = active_client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    upload_kwargs: dict[str, Any] = {"content_type": content_type}
    if if_generation_match is not None:
        upload_kwargs["if_generation_match"] = int(if_generation_match)
    blob.upload_from_filename(str(file_path), **upload_kwargs)
    return {
        "bucket": bucket_name,
        "object_path": object_path,
        "target_gcs_uri": f"gs://{bucket_name}/{object_path}",
        "local_path": str(file_path),
        "if_generation_match": if_generation_match,
    }


def read_gcs_object_bytes(
    *,
    source_gcs_uri: str,
    client_factory: Callable[[], Any] | None = None,
    client: Any | None = None,
) -> bytes:
    bucket_name, object_path = parse_gcs_uri(source_gcs_uri)
    active_client = client or _build_storage_client(client_factory)
    bucket = active_client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    return blob.download_as_bytes()


def read_gcs_object_text(
    *,
    source_gcs_uri: str,
    encoding: str = "utf-8",
    client_factory: Callable[[], Any] | None = None,
    client: Any | None = None,
) -> str:
    payload = read_gcs_object_bytes(
        source_gcs_uri=source_gcs_uri,
        client_factory=client_factory,
        client=client,
    )
    return payload.decode(encoding)


def verify_gcs_object_matches_local_file(
    *,
    local_path: str | Path,
    target_gcs_uri: str,
    client_factory: Callable[[], Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    file_path = Path(local_path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Local verification file not found: {file_path}")

    local_payload = file_path.read_bytes()
    local_sha256 = hashlib.sha256(local_payload).hexdigest()

    try:
        remote_payload = read_gcs_object_bytes(
            source_gcs_uri=target_gcs_uri,
            client_factory=client_factory,
            client=client,
        )
    except Exception as exc:
        return {
            "target_gcs_uri": target_gcs_uri,
            "local_path": str(file_path),
            "local_sha256": local_sha256,
            "remote_sha256": None,
            "local_size_bytes": len(local_payload),
            "remote_size_bytes": None,
            "matched": False,
            "status": "FAILED",
            "error": str(exc),
        }

    remote_sha256 = hashlib.sha256(remote_payload).hexdigest()
    matched = local_sha256 == remote_sha256
    return {
        "target_gcs_uri": target_gcs_uri,
        "local_path": str(file_path),
        "local_sha256": local_sha256,
        "remote_sha256": remote_sha256,
        "local_size_bytes": len(local_payload),
        "remote_size_bytes": len(remote_payload),
        "matched": matched,
        "status": "VERIFIED" if matched else "MISMATCH",
    }
