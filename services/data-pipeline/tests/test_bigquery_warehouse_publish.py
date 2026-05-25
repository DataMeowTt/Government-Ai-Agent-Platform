from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from warehouse.bigquery_warehouse_publish import (
    promote_validated_candidate,
    publish_with_staging,
    stage_and_validate_candidate,
)
from warehouse.bigquery_recovery import (
    PRODUCTION_TABLE_ORDER,
    RecoveryCollisionError,
    build_recovery_plan,
    prepare_recovery_backups,
    recovery_table_id_for,
)


class _Writer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._staging_rows = 0
        self._production_rows = 0

    def get_table_layout(self, table_id: str) -> tuple[dict[str, int | str] | None, list[str] | None]:
        self.calls.append(("layout", table_id, ""))
        return None, ["country_code", "year"]

    def load_parquet(
        self,
        *,
        parquet_path: Path,
        table_id: str,
        range_partitioning: dict[str, int | str] | None = None,
        clustering_fields: list[str] | None = None,
    ) -> str:
        del range_partitioning, clustering_fields
        frame = pd.read_parquet(parquet_path)
        self._staging_rows = int(len(frame))
        self.calls.append(("load", table_id, str(parquet_path)))
        return "load-1"

    def get_table_info(self, table_id: str) -> tuple[int, list[str]]:
        self.calls.append(("table_info", table_id, ""))
        return self._staging_rows, ["country_code", "year", "run_id"]

    def copy_table(self, *, source_table_id: str, destination_table_id: str) -> str:
        self.calls.append(("copy", source_table_id, destination_table_id))
        self._production_rows = self._staging_rows
        return "copy-1"

    def count_rows(self, table_id: str) -> int:
        self.calls.append(("count", table_id, ""))
        return self._production_rows


def _parquet_fixture(tmp_path: Path, rows: int = 2) -> Path:
    frame = pd.DataFrame(
        [
            {"country_code": "VNM", "year": 2024, "run_id": "r1"},
            {"country_code": "THA", "year": 2024, "run_id": "r1"},
        ][:rows]
    )
    path = tmp_path / "candidate.parquet"
    frame.to_parquet(path, index=False)
    return path


def test_stage_and_validate_candidate_does_not_copy(tmp_path: Path) -> None:
    writer = _Writer()
    parquet_path = _parquet_fixture(tmp_path, rows=2)
    candidate = stage_and_validate_candidate(
        project_id="western-pivot-452008-a6",
        location="asia-southeast1",
        dataset="gov_ai_gold",
        staging_table="gold_growth_dynamics_staging_run_20260524_010203",
        production_table="gold_growth_dynamics",
        parquet_path=parquet_path,
        expected_required_columns=["country_code", "year", "run_id"],
        local_row_count=2,
        writer=writer,
    )

    assert candidate.staging_row_count == 2
    assert all(call[0] != "copy" for call in writer.calls)


def test_promote_validated_candidate_copies_once(tmp_path: Path) -> None:
    writer = _Writer()
    parquet_path = _parquet_fixture(tmp_path, rows=1)
    candidate = stage_and_validate_candidate(
        project_id="western-pivot-452008-a6",
        location="asia-southeast1",
        dataset="gov_ai_analytics",
        staging_table="analytics_clusters_staging_run_20260524_010203",
        production_table="analytics_clusters",
        parquet_path=parquet_path,
        expected_required_columns=["country_code", "year", "run_id"],
        local_row_count=1,
        writer=writer,
    )
    result = promote_validated_candidate(
        project_id="western-pivot-452008-a6",
        location="asia-southeast1",
        candidate=candidate,
        writer=writer,
    )

    assert result.production_row_count == 1
    assert any(call[0] == "copy" for call in writer.calls)


def test_publish_with_staging_keeps_legacy_behavior(tmp_path: Path) -> None:
    writer = _Writer()
    parquet_path = _parquet_fixture(tmp_path, rows=2)
    result = publish_with_staging(
        project_id="western-pivot-452008-a6",
        location="asia-southeast1",
        dataset="gov_ai_gold",
        staging_table="gold_social_welfare_staging_run_20260524_010203",
        production_table="gold_social_welfare",
        parquet_path=parquet_path,
        expected_required_columns=["country_code", "year", "run_id"],
        local_row_count=2,
        writer=writer,
    )

    assert result.staging_row_count == 2
    assert result.production_row_count == 2
    assert any(call[0] == "copy" for call in writer.calls)


def test_recovery_table_id_uses_sanitized_run_scope() -> None:
    table_id = recovery_table_id_for(
        "western-pivot-452008-a6.gov_ai_gold.gold_growth_dynamics",
        "controlled-refresh-2026-05-24T06:30:15Z",
    )
    assert table_id.endswith(".gold_growth_dynamics_recovery_run_controlled_refresh_2026_05_24T06_30_15Z")


def test_recovery_plan_covers_all_12_production_targets() -> None:
    plan = build_recovery_plan(production_table_ids=PRODUCTION_TABLE_ORDER, run_id="run-1")
    assert len(plan) == 12
    assert [item["production_table_id"] for item in plan] == PRODUCTION_TABLE_ORDER


class _RecoveryTable:
    def __init__(self, rows: int) -> None:
        self.num_rows = rows
        self.expires = None


class _RecoveryJob:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def result(self) -> None:
        return None


class _RecoveryClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self._existing = set(existing or set())
        self._rows: dict[str, int] = {}
        self.copy_calls: list[tuple[str, str, object]] = []
        self.updated_expirations: list[tuple[object, list[str]]] = []

    def get_table(self, table_id: str) -> _RecoveryTable:
        if table_id not in self._existing:
            raise RuntimeError("not found")
        return _RecoveryTable(self._rows.get(table_id, 1))

    def copy_table(self, source: str, destination: str, *, job_config: object, location: str) -> _RecoveryJob:
        del location
        self.copy_calls.append((source, destination, job_config))
        self._existing.add(destination)
        self._rows[source] = self._rows.get(source, 1)
        self._rows[destination] = self._rows[source]
        return _RecoveryJob("copy-recovery-1")

    def update_table(self, table: _RecoveryTable, fields: list[str]) -> _RecoveryTable:
        self.updated_expirations.append((table.expires, fields))
        return table


def test_prepare_recovery_backups_uses_non_overwrite_copy_and_retention() -> None:
    client = _RecoveryClient(existing=set(PRODUCTION_TABLE_ORDER))
    payload = prepare_recovery_backups(
        project_id="western-pivot-452008-a6",
        location="asia-southeast1",
        production_table_ids=PRODUCTION_TABLE_ORDER,
        run_id="run-1",
        retention_days=45,
        env_getter=lambda _: "true",
        client_factory=lambda _project_id: client,
    )
    assert payload["status"] == "RECOVERY_READY"
    assert payload["retention_days"] == 45
    assert len(payload["backups"]) == 12
    assert len(client.updated_expirations) == 12
    assert all(fields == ["expires"] for _, fields in client.updated_expirations)


def test_prepare_recovery_backups_collision_blocks_before_copy() -> None:
    first_recovery_id = recovery_table_id_for(PRODUCTION_TABLE_ORDER[0], "run-1")
    client = _RecoveryClient(existing=set(PRODUCTION_TABLE_ORDER) | {first_recovery_id})
    with pytest.raises(RecoveryCollisionError):
        prepare_recovery_backups(
            project_id="western-pivot-452008-a6",
            location="asia-southeast1",
            production_table_ids=PRODUCTION_TABLE_ORDER,
            run_id="run-1",
            retention_days=45,
            env_getter=lambda _: "true",
            client_factory=lambda _project_id: client,
        )
    assert client.copy_calls == []
