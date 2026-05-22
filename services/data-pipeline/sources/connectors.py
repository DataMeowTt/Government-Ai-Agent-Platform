from __future__ import annotations

import csv
import io
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from config.source_registry import SourceRegistryEntry


@dataclass(frozen=True)
class ConnectorPayload:
    input_kind: str
    source_uri: str
    payload_bytes: bytes
    output_format: str
    is_test_fixture: bool = False


def _csv_fixture_bytes(source_name: str) -> bytes:
    rows = [
        {
            "country_code": "USA",
            "country": "United States",
            "year": 2000,
            "indicator": f"{source_name}_fixture_metric",
            "value": "1.0",
            "source": "test_fixture",
        },
        {
            "country_code": "VNM",
            "country": "Viet Nam",
            "year": 2001,
            "indicator": f"{source_name}_fixture_metric",
            "value": "2.0",
            "source": "test_fixture",
        },
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["country_code", "country", "year", "indicator", "value", "source"],
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build_smoke_fixture(entry: SourceRegistryEntry) -> ConnectorPayload:
    return ConnectorPayload(
        input_kind="test_fixture",
        source_uri=f"fixture://{entry.source_name}/csv",
        payload_bytes=_csv_fixture_bytes(entry.source_name),
        output_format="csv",
        is_test_fixture=True,
    )


def read_local_file(path: str | Path) -> ConnectorPayload:
    file_path = Path(path).expanduser()
    payload_bytes = file_path.read_bytes()
    suffix = file_path.suffix.lower().lstrip(".")
    output_format = "json" if suffix == "json" else "csv"
    return ConnectorPayload(
        input_kind="local_path",
        source_uri=str(file_path),
        payload_bytes=payload_bytes,
        output_format=output_format,
        is_test_fixture=False,
    )


def copy_local_file(source_path: str | Path, destination_path: str | Path) -> None:
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(source_path), destination)


def download_csv_url(csv_url: str, destination_path: str | Path) -> ConnectorPayload:
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(csv_url) as response:
        payload_bytes = response.read()
    destination.write_bytes(payload_bytes)
    return ConnectorPayload(
        input_kind="csv_url",
        source_uri=csv_url,
        payload_bytes=payload_bytes,
        output_format="csv",
        is_test_fixture=False,
    )


def fetch_api_bytes(api_url: str) -> ConnectorPayload:
    with urlopen(api_url) as response:
        payload_bytes = response.read()
    parsed = urlparse(api_url)
    output_format = "json" if parsed.path.endswith(".json") else "json"
    return ConnectorPayload(
        input_kind="api",
        source_uri=api_url,
        payload_bytes=payload_bytes,
        output_format=output_format,
        is_test_fixture=False,
    )


def payload_to_text(payload: ConnectorPayload) -> str:
    if payload.output_format == "json":
        try:
            decoded = json.loads(payload.payload_bytes.decode("utf-8"))
            return json.dumps(decoded, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            return payload.payload_bytes.decode("utf-8", errors="replace")
    return payload.payload_bytes.decode("utf-8", errors="replace")
