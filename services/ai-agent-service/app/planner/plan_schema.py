from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueryPlan:
    question_type: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)