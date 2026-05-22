export type AiChatStatus =
  | 'success'
  | 'needs_clarification'
  | 'unsupported'
  | 'off_topic'
  | 'error'
  | (string & Record<never, never>);

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
  | 'UNSUPPORTED_DATA_QUERY'
  | (string & Record<never, never>);

export interface AiAgentChartConfig {
  type: 'line' | 'bar' | 'scatter' | 'table' | 'none' | (string & Record<never, never>);
  title?: string | null;
  xKey?: string | null;
  yKeys?: string[] | null;
  data?: Record<string, unknown>[] | null;
}

export interface AiAgentParsedQuery {
  intent?: string;
  question_family?: string;
  indicators?: string[];
  countries?: string[];
  country_groups?: string[];
  start_year?: number | null;
  end_year?: number | null;
  ranking_order?: string | null;
  limit?: number | null;
  threshold?: number | null;
  needs_clarification?: boolean;
  clarification_questions?: string[];
  confidence?: number;
  [key: string]: unknown;
}

export interface AiAgentRouterDebug {
  route?: string;
  confidence?: number;
  needs_parser?: boolean;
  needs_db?: boolean;
  uses_previous_result?: boolean;
  rewritten_query?: string | null;
  reason?: string | null;
  source?: string;
  attempts?: number;
  [key: string]: unknown;
}

export interface AiAgentParserDebug {
  source?: string;
  safe_to_execute?: boolean;
  catalog_pass?: boolean;
  schema_pass?: boolean;
  deployment_schema_pass?: boolean;
  latency_ms?: number;
  fallback_reason?: string | null;
  [key: string]: unknown;
}

export interface AiChatResponse {
  answer: string;
  questionType?: AiAgentQuestionType;
  status?: AiChatStatus;
  data?: Record<string, unknown>[];
  chart?: AiAgentChartConfig;
  parsedQuery?: AiAgentParsedQuery | null;
  parserDebug?: AiAgentParserDebug | null;
  routerDebug?: AiAgentRouterDebug | null;
  clarificationQuestions?: string[];
  warnings?: string[];
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AiChatRequest {
  message: string;
  conversationId: string;
  context?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  response?: AiChatResponse;
  status?: 'sending' | 'success' | 'error';
  error?: string;
}
