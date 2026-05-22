import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="min-h-screen flex-1 transition-all duration-300 lg:ml-64">
        <Header />
        <div className="mx-auto w-full max-w-[1440px] p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
