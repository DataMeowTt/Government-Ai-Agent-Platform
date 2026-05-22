import { AlertTriangle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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

function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="text-sm leading-6 text-slate-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          h1: ({ children }) => <h1 className="mb-2 mt-4 text-lg font-semibold text-slate-950 first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-4 text-base font-semibold text-slate-950 first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-3 text-sm font-semibold text-slate-950 first:mt-0">{children}</h3>,
          h4: ({ children }) => <h4 className="mb-2 mt-3 text-sm font-semibold text-slate-900 first:mt-0">{children}</h4>,
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-1">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-slate-950">{children}</strong>,
          em: ({ children }) => <em className="italic text-slate-800">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-4 border-slate-300 bg-slate-50 px-3 py-2 text-slate-700">
              {children}
            </blockquote>
          ),
          code: ({ children, className }) => {
            if (className) {
              return <code className={className}>{children}</code>;
            }
            return (
              <code className="rounded border border-slate-200 bg-slate-100 px-1 py-0.5 text-[0.85em] text-slate-900">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="my-3 overflow-x-auto rounded-md border border-slate-200 bg-slate-950 p-3 text-xs leading-5 text-slate-50">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-md border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
          tbody: ({ children }) => <tbody className="divide-y divide-slate-100 bg-white">{children}</tbody>,
          th: ({ children }) => (
            <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold text-slate-600">{children}</th>
          ),
          td: ({ children }) => <td className="whitespace-nowrap px-3 py-2 text-slate-700">{children}</td>,
          a: ({ children, href }) => (
            <a href={href} className="font-medium text-blue-700 underline underline-offset-2" target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
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

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <AssistantMarkdown content={message.content} />

        {message.error ? (
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {message.error}
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
