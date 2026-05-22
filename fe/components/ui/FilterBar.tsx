import { ReactNode } from 'react';
import { cn } from '@/lib/utils/cn';

interface FilterBarProps {
  children: ReactNode;
  className?: string;
}

export default function FilterBar({ children, className }: FilterBarProps) {
  return (
    <div className={cn('rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm', className)}>
      <div className="grid gap-3 md:grid-cols-12 md:items-end">{children}</div>
    </div>
  );
}
