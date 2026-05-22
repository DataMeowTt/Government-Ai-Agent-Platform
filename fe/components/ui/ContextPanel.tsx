import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

interface ContextItem {
  icon: LucideIcon;
  label: string;
  value?: string;
  status?: 'ok' | 'warning' | 'error';
}

interface ContextPanelProps {
  title: string;
  items: ContextItem[];
  actions?: { label: string; onClick: () => void; variant?: 'primary' | 'secondary' }[];
  className?: string;
}

export default function ContextPanel({ title, items, actions, className }: ContextPanelProps) {
  return (
    <div className={cn('bg-white rounded-md border border-gray-200 p-5 space-y-4', className)}>
      <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      <div className="space-y-3">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <item.icon className="w-4 h-4 text-gray-400" />
              {item.label}
            </div>
            <span className={cn(
              'text-sm font-medium px-2 py-0.5 rounded',
              item.status === 'ok' ? 'text-emerald-700 bg-emerald-50' :
              item.status === 'warning' ? 'text-amber-700 bg-amber-50' :
              item.status === 'error' ? 'text-rose-700 bg-rose-50' :
              'text-gray-900'
            )}>
              {item.value || '-'}
            </span>
          </div>
        ))}
      </div>
      {actions && (
        <div className="pt-4 border-t border-gray-100 flex gap-3">
          {actions.map((action, idx) => (
            <button
              key={idx}
              onClick={action.onClick}
              className={cn(
                'px-4 py-2 text-sm font-medium rounded-md transition-colors w-full',
                action.variant === 'primary' ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-50 text-gray-700 border border-gray-200 hover:bg-gray-100'
              )}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}