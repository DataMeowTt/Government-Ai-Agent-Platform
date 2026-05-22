export type AiAgentQuestionType =
  | 'OFF_TOPIC'
  | 'NEED_CLARIFICATION'
  | 'VALID_SIMPLE_QUERY'
  | 'VALID_COMPARE_QUERY'
  | 'VALID_RANKING_QUERY'
  | 'VALID_TREND_QUERY'
  | 'VALID_ANOMALY_QUERY'
  | 'VALID_COVERAGE_QUERY'
  | 'UNSUPPORTED'
  | 'UNSUPPORTED_DATA_QUERY';

export type AiAgentChatStatus =
  | 'success'
  | 'needs_clarification'
  | 'unsupported'
  | 'off_topic'
  | 'error'
  | (string & Record<never, never>);

export interface AiAgentChartConfig {
  type: 'line' | 'bar' | 'scatter' | 'table' | 'none';
  title?: string;
  xKey?: string;
  yKeys?: string[];
  data?: Record<string, unknown>[];
}

export interface AiAgentRouterDebug {
  route?: string;
  confidence?: number;
  needs_parser?: boolean;
  needs_db?: boolean;
  uses_previous_result?: boolean;
  answer?: string | null;
  answer_strategy?: string | null;
  rewritten_query?: string | null;
  clarification_question?: string | null;
  reason?: string | null;
  source?: string;
  attempts?: number;
  [key: string]: unknown;
}

export interface AiAgentParserDebug {
  mode?: string;
  source?: string;
  safe_to_execute?: boolean;
  catalog_pass?: boolean;
  schema_pass?: boolean;
  deployment_schema_pass?: boolean;
  fallback_reason?: string | null;
  latency_ms?: number;
  inference_mode?: string;
  [key: string]: unknown;
}

export interface AiAgentParsedQuery {
  intent?: string;
  question_family?: string;
  indicators?: string[];
  countries?: string[];
  country_groups?: string[];
  start_year?: number | null;
  end_year?: number | null;
  relative_time?: string | null;
  event_time?: string | null;
  ranking_order?: 'asc' | 'desc' | (string & Record<never, never>) | null;
  limit?: number | null;
  threshold?: number | null;
  aggregation?: string | null;
  chart_preference?: string | null;
  needs_clarification?: boolean;
  clarification_questions?: string[];
  confidence?: number;
  [key: string]: unknown;
}

export interface AiAgentMetadata {
  source?: 'template' | 'gemini' | 'mock' | (string & Record<never, never>);
  toolsUsed?: string[];
  indicators?: string[];
  analytics_indicators?: string[];
  raw_only_indicators?: string[];
  countries?: string[];
  years?: number[];
  resolved?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface AiAgentChatResponse {
  answer: string;
  questionType?: AiAgentQuestionType;
  status?: AiAgentChatStatus;
  data?: Record<string, unknown>[];
  chart?: AiAgentChartConfig;
  parsedQuery?: AiAgentParsedQuery | null;
  parserDebug?: AiAgentParserDebug | null;
  routerDebug?: AiAgentRouterDebug | null;
  clarificationQuestions?: string[];
  warnings?: string[];
  metadata?: AiAgentMetadata;
  [key: string]: unknown;
}

export interface AiAgentHealthResponse {
  status: 'ok' | 'degraded' | 'error';
  service: string;
  version?: string;
}
