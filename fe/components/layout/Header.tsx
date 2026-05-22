'use client';
import { useUIStore } from '@/lib/stores/uiStore';
import Breadcrumbs from '@/components/ui/Breadcrumbs';
import { Menu } from 'lucide-react';

export default function Header() {
  const { isSidebarOpen, setSidebarOpen } = useUIStore();

  return (
    <header className="sticky top-0 z-30 h-16 border-b border-slate-200 bg-white px-6">
      <div className="flex h-full items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setSidebarOpen(!isSidebarOpen)}
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Breadcrumbs />
        </div>
        <div className="hidden items-center gap-2 rounded border border-slate-200 bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 md:flex">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          Trạng thái dữ liệu: sẵn sàng
        </div>
      </div>
    </header>
  );
}
