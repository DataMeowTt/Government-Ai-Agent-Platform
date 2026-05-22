import { cn } from '@/lib/utils/cn';
import { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  icon: LucideIcon;
  title: string;
  value: string | number;
  trend?: { value: string; direction: 'up' | 'down' };
  action?: { label: string; href: string };
  className?: string;
  isLoading?: boolean;
}

export default function MetricCard({ icon: Icon, title, value, trend, action, className, isLoading }: MetricCardProps) {
  if (isLoading) {
    return (
      <div className={cn('h-[140px] bg-white rounded-md border border-gray-200 p-6 flex flex-col justify-between', className)}>
        <div className="h-4 w-24 bg-gray-200 animate-pulse rounded" />
        <div className="h-8 w-20 bg-gray-200 animate-pulse rounded mt-4" />
        <div className="h-4 w-32 bg-gray-200 animate-pulse rounded mt-6" />
      </div>
    );
  }
  return (
    <div className={cn('bg-white max-h-[200px] rounded-md border border-gray-200 p-6 flex flex-col justify-between transition-shadow hover:shadow-md', className)}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-50 rounded-md text-blue-600">
            <Icon className="w-5 h-5" />
          </div>
          <span className="text-sm font-medium text-gray-600">{title}</span>
        </div>
      </div>
      <div className="mt-4 flex items-end justify-between">
        <span className="text-3xl font-bold text-gray-900">{value}</span>
        {trend && (
          <div className={cn('text-xs font-medium px-2 py-1 rounded-full',
            trend.direction === 'up' ? 'text-emerald-700 bg-emerald-50' : 'text-rose-700 bg-rose-50'
          )}>
            {trend.value}
          </div>
        )}
      </div>
      {action && (
        <a href={action.href} className="text-sm text-blue-600 hover:text-blue-700 font-medium mt-4 inline-flex items-center gap-1">
          {action.label}
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      )}
    </div>
  );
}