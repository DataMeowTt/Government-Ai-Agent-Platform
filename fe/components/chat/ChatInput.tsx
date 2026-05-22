'use client';

import { FormEvent, KeyboardEvent } from 'react';
import { Loader2, Plus, Send } from 'lucide-react';

interface ChatInputProps {
  value: string;
  isLoading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onNewChat: () => void;
}

export default function ChatInput({ value, isLoading, onChange, onSubmit, onNewChat }: ChatInputProps) {
  const canSend = value.trim().length > 0 && !isLoading;
  const textareaId = 'chat-message-input';

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canSend) {
      onSubmit();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (canSend) {
        onSubmit();
      }
    }
  }

  return (
    <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white p-4">
      <div className="flex gap-3">
        <label htmlFor={textareaId} className="sr-only">
          Nhập nội dung chat
        </label>
        <textarea
          id={textareaId}
          name="message"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Nhập câu hỏi về dữ liệu kinh tế..."
          rows={2}
          className="min-h-[52px] flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />
        <div className="flex h-[52px] items-center gap-2">
          <button
            type="button"
            onClick={onNewChat}
            className="inline-flex h-[52px] items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Plus className="h-4 w-4" />
            New chat
          </button>
          <button
            type="submit"
            disabled={!canSend}
            className="inline-flex h-[52px] items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Gửi
          </button>
        </div>
      </div>
    </form>
  );
}
