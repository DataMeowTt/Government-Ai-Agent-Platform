import Link from 'next/link';
import { ReactNode } from 'react';

interface StatCardProps {
  label: string;
  value: string;
  note?: string;
  icon?: ReactNode;
  href?: string;
}

export default function StatCard({ label, value, note, icon, href }: StatCardProps) {
  const content = (
    <div className="rounded-md border border-slate-200 bg-white px-4 py-4 shadow-sm transition-colors hover:border-slate-300">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-600">{label}</p>
        {icon ? <div className="text-slate-500">{icon}</div> : null}
      </div>
      <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
      {note ? <p className="mt-1 text-xs text-slate-500">{note}</p> : null}
    </div>
  );

  if (!href) return content;
  return <Link href={href}>{content}</Link>;
}
