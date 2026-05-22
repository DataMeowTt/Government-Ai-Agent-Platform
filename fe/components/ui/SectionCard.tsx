import { ReactNode } from 'react';
import { cn } from '@/lib/utils/cn';

interface SectionCardProps {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

export default function SectionCard({ title, description, children, className }: SectionCardProps) {
  return (
    <section className={cn('rounded-md border border-slate-200 bg-white shadow-sm', className)}>
      {title || description ? (
        <header className="border-b border-slate-200 px-5 py-4">
          {title ? <h2 className="text-base font-semibold text-slate-900">{title}</h2> : null}
          {description ? <p className="mt-1 text-sm text-slate-600">{description}</p> : null}
        </header>
      ) : null}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}
