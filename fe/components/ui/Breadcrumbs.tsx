'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const routeMap: Record<string, string> = {
  '/countries': 'Quốc gia',
  '/compare': 'So sánh',
  '/clusters': 'Nhóm cấu trúc',
  '/anomalies': 'Bất thường',
  '/indicators': 'Danh mục chỉ số',
  '/chat': 'Trợ lý dữ liệu AI',
};

export default function Breadcrumbs({ className }: { className?: string }) {
  const pathname = usePathname();
  const segments = pathname.split('/').filter(Boolean);

  if (segments.length === 0) return null;

  const items = segments.map((segment, index) => {
    const path = `/${segments.slice(0, index + 1).join('/')}`;
    const base = routeMap[path];
    const label =
      base ||
      (segments[index - 1] === 'countries' ? `Hồ sơ ${segment.toUpperCase()}` : segment.toUpperCase());
    return { label, path };
  });

  return (
    <nav className={cn('flex items-center gap-2 text-sm text-slate-600', className)} aria-label="Breadcrumb">
      <Link href="/" className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800">
        <Home className="h-4 w-4" />
      </Link>
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <div key={item.path} className="flex items-center gap-2">
            <ChevronRight className="h-4 w-4 text-slate-400" />
            {isLast ? (
              <span className="font-medium text-slate-900">{item.label}</span>
            ) : (
              <Link href={item.path} className="hover:text-slate-900">
                {item.label}
              </Link>
            )}
          </div>
        );
      })}
    </nav>
  );
}
