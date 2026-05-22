from typing import Any, Literal

from pydantic import BaseModel, Field


QuestionType = Literal[
    "OFF_TOPIC",
    "NEED_CLARIFICATION",
    "VALID_SIMPLE_QUERY",
    "VALID_COMPARE_QUERY",
    "VALID_RANKING_QUERY",
    "VALID_TREND_QUERY",
    "VALID_ANOMALY_QUERY",
    "VALID_COVERAGE_QUERY",
    "NO_DATA",
    "UNSUPPORTED",
    "UNSUPPORTED_DATA_QUERY",
]


ChartType = Literal[
    "line",
    "bar",
    "scatter",
    "table",
    "none",
]


class AiChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversationId: str | None = None
    context: dict[str, Any] | None = None


class AiAgentChartConfig(BaseModel):
    type: ChartType = "none"
    title: str | None = None
    xKey: str | None = None
    yKeys: list[str] | None = None
    data: list[dict[str, Any]] | None = None


class AiAgentMetadata(BaseModel):
    source: Literal["template", "gemini", "mock"] = "mock"
    toolsUsed: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    analytics_indicators: list[str] = Field(default_factory=list)
    raw_only_indicators: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    resolved: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    resultValidation: dict[str, Any] | None = None
    ruleFirst: dict[str, Any] | None = None
    parserAgent: dict[str, Any] | None = None
    unsupportedTerms: list[str] = Field(default_factory=list)
    missingCountries: list[str] = Field(default_factory=list)
    pipeline: str | None = None
    fallbackUsed: bool | None = None


class AiChatResponse(BaseModel):
    answer: str
    questionType: QuestionType = "VALID_SIMPLE_QUERY"
    status: str = "success"
    data: list[dict[str, Any]] = Field(default_factory=list)
    chart: AiAgentChartConfig = Field(default_factory=AiAgentChartConfig)
    parsedQuery: dict[str, Any] | None = None
    parserDebug: dict[str, Any] | None = None
    routerDebug: dict[str, Any] | None = None
    clarificationQuestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: AiAgentMetadata = Field(default_factory=AiAgentMetadata)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"] = "ok"
    service: str
    version: str
