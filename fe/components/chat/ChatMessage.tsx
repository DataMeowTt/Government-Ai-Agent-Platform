import { AlertTriangle } from 'lucide-react';
import ChatDataTable from '@/components/chat/ChatDataTable';
import type { ChatMessage as ChatMessageType } from '@/lib/types/aiChat';

interface ChatMessageProps {
  message: ChatMessageType;
  onClarificationClick: (question: string) => void;
}

function renderText(content: string) {
  return content.split('\n').map((line, index) => (
    <span key={`${index}-${line}`}>
      {line}
      <br />
    </span>
  ));
}

export default function ChatMessage({ message, onClarificationClick }: ChatMessageProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-blue-600 px-4 py-3 text-sm leading-6 text-white">
          {renderText(message.content)}
        </div>
      </div>
    );
  }

  const response = message.response;
  const clarificationQuestions =
    response?.clarificationQuestions?.length
      ? response.clarificationQuestions
      : response?.parsedQuery?.clarification_questions || [];

  const countries = Array.isArray(response?.parsedQuery?.countries) ? response?.parsedQuery?.countries : [];
  const indicators = Array.isArray(response?.parsedQuery?.indicators) ? response?.parsedQuery?.indicators : [];
  const startYear = response?.parsedQuery?.start_year;
  const endYear = response?.parsedQuery?.end_year;
  const responseDataRows = Array.isArray(response?.data) ? response.data.length : 0;
  const chartRows = Array.isArray(response?.chart?.data) ? response.chart.data.length : 0;
  const rowCount = responseDataRows || chartRows || 0;
  const hasDataSummary = countries.length > 0 || indicators.length > 0 || startYear != null || endYear != null || rowCount > 0;

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="text-sm leading-6 text-slate-800">{renderText(message.content)}</div>

        {message.error ? (
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {message.error}
          </div>
        ) : null}

        {hasDataSummary ? (
          <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <p className="font-semibold text-slate-800">Dữ liệu đã sử dụng</p>
            {countries.length > 0 ? <p>Quốc gia: {countries.join(', ')}</p> : null}
            {indicators.length > 0 ? <p>Chỉ số: {indicators.join(', ')}</p> : null}
            {startYear != null || endYear != null ? (
              <p>
                Giai đoạn: {startYear ?? '...'} - {endYear ?? '...'}
              </p>
            ) : null}
            {rowCount > 0 ? <p>Số dòng dữ liệu: {rowCount}</p> : null}
          </div>
        ) : null}

        {clarificationQuestions.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {clarificationQuestions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => onClarificationClick(question)}
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-left text-xs font-medium text-amber-800 hover:bg-amber-100"
              >
                {question}
              </button>
            ))}
          </div>
        ) : null}

        {response?.warnings?.length ? (
          <div className="mt-4 space-y-2">
            {response.warnings.map((warning) => (
              <div
                key={warning}
                className="flex gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{warning}</span>
              </div>
            ))}
          </div>
        ) : null}
        <ChatDataTable response={response} />
      </div>
    </div>
  );
}
