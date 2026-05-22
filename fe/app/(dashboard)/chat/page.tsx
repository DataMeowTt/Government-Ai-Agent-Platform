'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import axios from 'axios';
import { Loader2, MessageSquareText } from 'lucide-react';
import ChatInput from '@/components/chat/ChatInput';
import ChatMessage from '@/components/chat/ChatMessage';
import { useAiChat } from '@/lib/hooks/useAiChat';
import type { ChatMessage as ChatMessageType } from '@/lib/types/aiChat';
import { TableSkeleton } from '@/components/ui/Skeletons';

const conversationStorageKey = 'gov-ai-chat-conversation-id';
const messagesStorageKey = 'gov-ai-chat-messages';

const suggestedPrompts = [
  'So sánh nợ công Việt Nam và Thái Lan từ 2010 đến 2023',
  'Top 10 nước có lạm phát CPI cao nhất năm 2020',
  'Nợ công/GDP là gì?',
];

const followupPrompts = [
  'Phân tích nguyên nhân chính của xu hướng này',
  'Mở rộng thêm Indonesia',
  'Đổi sang giai đoạn 2015 đến 2023',
];

function createId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createConversationId() {
  return `conversation-${createId()}`;
}

function isChatMessage(value: unknown): value is ChatMessageType {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === 'string' &&
    (record.role === 'user' || record.role === 'assistant') &&
    typeof record.content === 'string' &&
    typeof record.createdAt === 'string'
  );
}

function readStoredMessages() {
  try {
    const raw = localStorage.getItem(messagesStorageKey);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isChatMessage).slice(-30) : [];
  } catch {
    return [];
  }
}

function getErrorMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    return `Không thể xử lý yêu cầu lúc này. ${error.response?.status ? `(Mã ${error.response.status})` : ''}`;
  }
  return 'Không thể gửi câu hỏi tới trợ lý dữ liệu AI.';
}

export default function ChatPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={6} />}>
      <ChatPageContent />
    </Suspense>
  );
}

function ChatPageContent() {
  const searchParams = useSearchParams();
  const prefillPrompt = searchParams.get('q') || '';

  const [conversationId, setConversationId] = useState('');
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [input, setInput] = useState('');
  const [isHydrated, setIsHydrated] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatMutation = useAiChat();

  useEffect(() => {
    const storedConversationId = localStorage.getItem(conversationStorageKey);
    const nextConversationId = storedConversationId || createConversationId();
    localStorage.setItem(conversationStorageKey, nextConversationId);
    setConversationId(nextConversationId);
    setMessages(readStoredMessages());
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    localStorage.setItem(messagesStorageKey, JSON.stringify(messages.slice(-30)));
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [isHydrated, messages]);

  useEffect(() => {
    if (!prefillPrompt) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInput(prefillPrompt);
  }, [prefillPrompt]);

  const hasAssistantResponse = useMemo(
    () => messages.some(item => item.role === 'assistant' && item.status !== 'error'),
    [messages],
  );

  async function handleSubmit() {
    const message = input.trim();
    if (!message || chatMutation.isPending) return;

    const activeConversationId = conversationId || createConversationId();
    if (!conversationId) {
      setConversationId(activeConversationId);
      localStorage.setItem(conversationStorageKey, activeConversationId);
    }

    setInput('');
    const userMessage: ChatMessageType = {
      id: createId(),
      role: 'user',
      content: message,
      createdAt: new Date().toISOString(),
      status: 'success',
    };
    setMessages(current => [...current, userMessage].slice(-30));

    try {
      const response = await chatMutation.mutateAsync({
        message,
        conversationId: activeConversationId,
      });

      const assistantMessage: ChatMessageType = {
        id: createId(),
        role: 'assistant',
        content: response.answer || 'Không có phản hồi từ trợ lý dữ liệu AI.',
        createdAt: new Date().toISOString(),
        response,
        status: 'success',
      };
      setMessages(current => [...current, assistantMessage].slice(-30));
    } catch (error) {
      const assistantMessage: ChatMessageType = {
        id: createId(),
        role: 'assistant',
        content: 'Không thể nhận phản hồi từ trợ lý dữ liệu AI.',
        createdAt: new Date().toISOString(),
        status: 'error',
        error: getErrorMessage(error),
      };
      setMessages(current => [...current, assistantMessage].slice(-30));
    }
  }

  function handleNewChat() {
    const nextConversationId = createConversationId();
    setConversationId(nextConversationId);
    setMessages([]);
    setInput(prefillPrompt || '');
    localStorage.setItem(conversationStorageKey, nextConversationId);
    localStorage.removeItem(messagesStorageKey);
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1 border-b border-slate-200 pb-4">
        <h1 className="text-2xl font-semibold text-slate-900">Trợ lý phân tích dữ liệu</h1>
        <p className="text-sm text-slate-600">
          Đặt câu hỏi bằng ngôn ngữ tự nhiên về quốc gia, chỉ số, so sánh theo năm và diễn giải xu hướng dữ liệu.
        </p>
      </div>

      <section className="flex min-h-[700px] flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 p-4">
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <div className="max-w-md text-center">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded bg-slate-100 text-slate-600">
                  <MessageSquareText className="h-5 w-5" />
                </div>
                <h2 className="text-base font-semibold text-slate-900">Bắt đầu trao đổi với trợ lý</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Khuyến nghị bắt đầu bằng câu hỏi đầy đủ quốc gia, chỉ số và giai đoạn năm để tăng độ chính xác.
                </p>
              </div>
            </div>
          ) : (
            messages.map(message => (
              <ChatMessage key={message.id} message={message} onClarificationClick={setInput} />
            ))
          )}

          {chatMutation.isPending ? (
            <div className="flex justify-start">
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <Loader2 className="h-5 w-5 animate-spin text-slate-600" aria-label="Đang xử lý" />
              </div>
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {suggestedPrompts.map(prompt => (
              <button
                key={prompt}
                type="button"
                onClick={() => setInput(prompt)}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
              >
                {prompt}
              </button>
            ))}
          </div>
          {hasAssistantResponse ? (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {followupPrompts.map(prompt => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setInput(prompt)}
                  className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <ChatInput
          value={input}
          isLoading={chatMutation.isPending}
          onChange={setInput}
          onSubmit={handleSubmit}
          onNewChat={handleNewChat}
        />
      </section>
    </div>
  );
}
