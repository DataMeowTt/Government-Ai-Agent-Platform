import type { AiChatStatus } from '@/lib/types/aiChat';

const statusStyles: Record<string, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  needs_clarification: 'border-amber-200 bg-amber-50 text-amber-700',
  unsupported: 'border-slate-200 bg-slate-100 text-slate-700',
  off_topic: 'border-amber-200 bg-amber-50 text-amber-700',
  error: 'border-red-200 bg-red-50 text-red-700',
};

export default function StatusBadge({ status }: { status?: AiChatStatus }) {
  const label = status || 'success';
  const className = statusStyles[label] || 'border-slate-200 bg-slate-50 text-slate-700';
  const textMap: Record<string, string> = {
    success: 'Thành công',
    needs_clarification: 'Cần làm rõ',
    unsupported: 'Không hỗ trợ',
    off_topic: 'Ngoài phạm vi',
    error: 'Lỗi',
  };

  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${className}`}>
      {textMap[label] || label}
    </span>
  );
}
