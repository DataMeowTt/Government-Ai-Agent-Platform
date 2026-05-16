from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class AnalyticsWritePlan:
    target: str
    table: str
    table_id: str
    required_columns: tuple[str, ...]
    source_table: str | None = None
    indicators: tuple[str, ...] = ()
    cluster_years: tuple[int, ...] = ()
    latest_valid_year: int | None = None
    project_id: str | None = None
    dataset: str | None = None
    location: str | None = None
    dry_run: bool = True
    job_started: bool = False
    note: str = "dry_run=true; no warehouse job was started."

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["required_columns"] = list(self.required_columns)
        payload["indicators"] = list(self.indicators)
        payload["cluster_years"] = list(self.cluster_years)
        return payload


class AnalyticsOutputAdapter(Protocol):
    target: str
    supports_dry_run: bool

    def build_indicator_plan(
        self,
        source_table: str,
        indicators: list[str],
        *,
        dry_run: bool,
    ) -> AnalyticsWritePlan:
        ...

    def build_cluster_plan(
        self,
        cluster_years: list[int],
        *,
        dry_run: bool,
        latest_valid_year: int | None = None,
    ) -> AnalyticsWritePlan:
        ...

    def ensure_can_execute(self, *, dry_run: bool) -> None:
        ...
