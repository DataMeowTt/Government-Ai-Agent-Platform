from __future__ import annotations

from pathlib import Path

import pytest

from sources.gcs_runtime_client import (
    parse_gcs_uri,
    read_gcs_object_bytes,
    read_gcs_object_text,
    upload_file_to_gcs_uri,
    verify_gcs_object_matches_local_file,
)
from sources.gcs_upload import execute_upload_plan


class _FakeBlob:
    def __init__(self, name: str, storage: dict[str, bytes], calls: dict[str, list[str]]) -> None:
        self._name = name
        self._storage = storage
        self._calls = calls

    def upload_from_filename(
        self,
        filename: str,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> None:
        payload = Path(filename).read_bytes()
        self._storage[self._name] = payload
        self._calls["writes"].append(f"{self._name}|{content_type or ''}|{if_generation_match}")

    def download_as_bytes(self) -> bytes:
        self._calls["reads"].append(self._name)
        if self._name not in self._storage:
            raise FileNotFoundError(self._name)
        return self._storage[self._name]


class _FakeBucket:
    def __init__(self, storage: dict[str, bytes], calls: dict[str, list[str]]) -> None:
        self._storage = storage
        self._calls = calls

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(name, self._storage, self._calls)


class _FakeClient:
    def __init__(self, storage: dict[str, bytes], calls: dict[str, list[str]]) -> None:
        self._storage = storage
        self._calls = calls

    def bucket(self, _bucket_name: str) -> _FakeBucket:
        return _FakeBucket(self._storage, self._calls)


def test_parse_gcs_uri_valid_and_invalid_cases() -> None:
    bucket, object_path = parse_gcs_uri("gs://bucket/path/to/object.json")
    assert bucket == "bucket"
    assert object_path == "path/to/object.json"
    with pytest.raises(ValueError):
        parse_gcs_uri("https://example.com/not-gcs")
    with pytest.raises(ValueError):
        parse_gcs_uri("gs://bucket")


def test_read_only_fetch_reads_exact_manifest_uri_without_write_mutation() -> None:
    calls = {"reads": [], "writes": []}
    storage = {"manifests/source_manifest/run_date=2026-05-01/source_manifest.json": b'{"ok":true}\n'}
    client = _FakeClient(storage, calls)
    uri = "gs://bucket/manifests/source_manifest/run_date=2026-05-01/source_manifest.json"
    payload_bytes = read_gcs_object_bytes(source_gcs_uri=uri, client=client)
    payload_text = read_gcs_object_text(source_gcs_uri=uri, client=client)
    assert payload_bytes == b'{"ok":true}\n'
    assert payload_text == '{"ok":true}\n'
    assert calls["reads"] == [
        "manifests/source_manifest/run_date=2026-05-01/source_manifest.json",
        "manifests/source_manifest/run_date=2026-05-01/source_manifest.json",
    ]
    assert calls["writes"] == []


def test_approved_upload_uses_python_runtime_seam_and_no_subprocess(tmp_path: Path) -> None:
    local_file = tmp_path / "source_manifest.json"
    local_file.write_text('{"status":"ok"}\n', encoding="utf-8")
    calls = {"reads": [], "writes": []}
    storage: dict[str, bytes] = {}
    client = _FakeClient(storage, calls)
    upload_file_to_gcs_uri(
        local_path=local_file,
        target_gcs_uri="gs://bucket/manifests/source_manifest/run_date=2026-05-24/source_manifest.json",
        content_type="application/json",
        if_generation_match=0,
        client=client,
    )
    assert calls["writes"] == ["manifests/source_manifest/run_date=2026-05-24/source_manifest.json|application/json|0"]


def test_execute_upload_plan_uses_uploader_callback_for_approved_writes(tmp_path: Path) -> None:
    local_file = tmp_path / "file.txt"
    local_file.write_text("payload\n", encoding="utf-8")
    upload_calls: list[tuple[str, str]] = []

    def fake_uploader(
        *,
        local_path: str | Path,
        target_gcs_uri: str,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> dict:
        del content_type
        upload_calls.append((str(local_path), target_gcs_uri))
        assert if_generation_match == 0
        return {"ok": True}

    payload = execute_upload_plan(
        {
            "cloud_write_approved": True,
            "run_id": "run-1",
            "run_date": "2026-05-24",
            "gcs_bucket": "bucket",
            "objects": [
                {
                    "status": "planned",
                    "local_path": str(local_file),
                    "target_gcs_uri": "gs://bucket/path/file.txt",
                    "content_type": "text/plain",
                    "if_generation_match": 0,
                }
            ],
        },
        uploader=fake_uploader,
    )

    assert payload["status"] == "uploaded"
    assert payload["uploaded_count"] == 1
    assert upload_calls == [(str(local_file), "gs://bucket/path/file.txt")]


def test_verify_gcs_object_matches_local_file_verified(tmp_path: Path) -> None:
    local_file = tmp_path / "source_manifest.json"
    local_file.write_text('{"status":"ok"}\n', encoding="utf-8")
    calls = {"reads": [], "writes": []}
    object_name = "manifests/source_manifest/run_date=2026-05-24/source_manifest.json"
    storage = {object_name: local_file.read_bytes()}
    client = _FakeClient(storage, calls)

    payload = verify_gcs_object_matches_local_file(
        local_path=local_file,
        target_gcs_uri=f"gs://bucket/{object_name}",
        client=client,
    )

    assert payload["status"] == "VERIFIED"
    assert payload["matched"] is True
    assert payload["local_sha256"] == payload["remote_sha256"]
    assert payload["local_size_bytes"] == payload["remote_size_bytes"]


def test_verify_gcs_object_matches_local_file_mismatch(tmp_path: Path) -> None:
    local_file = tmp_path / "source_manifest.json"
    local_file.write_text('{"status":"ok"}\n', encoding="utf-8")
    calls = {"reads": [], "writes": []}
    object_name = "manifests/source_manifest/run_date=2026-05-24/source_manifest.json"
    storage = {object_name: b'{"status":"changed"}\n'}
    client = _FakeClient(storage, calls)

    payload = verify_gcs_object_matches_local_file(
        local_path=local_file,
        target_gcs_uri=f"gs://bucket/{object_name}",
        client=client,
    )

    assert payload["status"] == "MISMATCH"
    assert payload["matched"] is False
    assert payload["local_sha256"] != payload["remote_sha256"]


def test_verify_gcs_object_matches_local_file_remote_read_failure(tmp_path: Path) -> None:
    local_file = tmp_path / "source_manifest.json"
    local_file.write_text('{"status":"ok"}\n', encoding="utf-8")
    calls = {"reads": [], "writes": []}
    client = _FakeClient({}, calls)
    object_name = "manifests/source_manifest/run_date=2026-05-24/source_manifest.json"

    payload = verify_gcs_object_matches_local_file(
        local_path=local_file,
        target_gcs_uri=f"gs://bucket/{object_name}",
        client=client,
    )

    assert payload["status"] == "FAILED"
    assert payload["matched"] is False
    assert payload["remote_sha256"] is None
