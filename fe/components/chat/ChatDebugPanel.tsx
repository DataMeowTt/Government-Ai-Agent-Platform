'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { AiChatResponse } from '@/lib/types/aiChat';

function hasDebug(response?: AiChatResponse) {
  return Boolean(response?.routerDebug || response?.parserDebug || response?.parsedQuery || response?.metadata);
}

export default function ChatDebugPanel({ response }: { response?: AiChatResponse }) {
  const [isOpen, setIsOpen] = useState(false);

  if (process.env.NODE_ENV === 'production' || !hasDebug(response)) {
    return null;
  }

  const debugPayload = {
    routerDebug: response?.routerDebug ?? null,
    parserDebug: response?.parserDebug ?? null,
    parsedQuery: response?.parsedQuery ?? null,
    metadata: response?.metadata ?? null,
  };

  return (
    <div className="mt-4 rounded-md border border-slate-200 bg-slate-50">
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:text-slate-900"
      >
        {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        Thông tin kỹ thuật (dev)
      </button>
      {isOpen ? (
        <pre className="max-h-80 overflow-auto border-t border-slate-200 p-3 text-xs text-slate-700">
          {JSON.stringify(debugPayload, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
