import { ReactNode } from 'react';
import { cn } from '@/lib/utils/cn';

interface TableShellProps {
  children: ReactNode;
  className?: string;
}

export default function TableShell({ children, className }: TableShellProps) {
  return (
    <div className={cn('overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm', className)}>
      <div className="overflow-x-auto">{children}</div>
    </div>
  );
}
