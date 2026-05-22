"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUIStore } from "@/lib/stores/uiStore";
import {
  LayoutDashboard,
  Globe2,
  AlertTriangle,
  PieChart,
  BarChart3,
  MessageSquare,
  X,
  ListChecks,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";

const navItems = [
  { name: "Tổng quan", path: "/", icon: LayoutDashboard },
  { name: "Quốc gia", path: "/countries", icon: Globe2 },
  { name: "So sánh", path: "/compare", icon: BarChart3 },
  { name: "Nhóm cấu trúc", path: "/clusters", icon: PieChart },
  { name: "Bất thường", path: "/anomalies", icon: AlertTriangle },
  { name: "Danh mục chỉ số", path: "/indicators", icon: ListChecks },
  { name: "Trợ lý dữ liệu AI", path: "/chat", icon: MessageSquare },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { isSidebarOpen, setSidebarOpen } = useUIStore();

  return (
    <>
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
      <aside
        role="navigation"
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 transform transition-transform duration-300 lg:translate-x-0",
          isSidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex items-center justify-between h-16 px-4 border-b border-slate-200">
          <div>
            <h1 className="text-sm font-semibold text-slate-900">Nền tảng dữ liệu kinh tế</h1>
            <p className="text-xs text-slate-500">Government AI Agent Platform</p>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden p-1.5 text-gray-500 hover:text-gray-900 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.path || (item.path !== "/" && pathname.startsWith(item.path));
            return (
              <Link
                key={item.path}
                href={item.path}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-md transition-colors border",
                  isActive
                    ? "bg-slate-100 text-slate-900 border-slate-300"
                    : "text-slate-700 border-transparent hover:bg-slate-50 hover:border-slate-200"
                )}
              >
                <item.icon className="w-5 h-5 flex-shrink-0" />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
