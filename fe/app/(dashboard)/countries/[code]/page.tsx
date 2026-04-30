'use client';
import { useParams, useRouter } from 'next/navigation';
import { useCountryAnalytics } from '@/lib/hooks/useCountries';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine } from 'recharts';
import { ChartSkeleton, CardSkeleton } from '@/components/ui/Skeletons';
import Tabs from '@/components/ui/Tabs';
import ContextPanel from '@/components/ui/ContextPanel';
import { CountryAnalyticsRow } from '@/lib/types';
import { ArrowLeft, AlertTriangle, BarChart3, Download, TrendingUp, Activity } from 'lucide-react';

const prepareChartData = (data: CountryAnalyticsRow[], keys: string[]) => {
  return data
    .filter(d => keys.some(k => d[k as keyof CountryAnalyticsRow] != null))
    .map(d => {
      const point: Record<string, number | undefined> = { year: d.year };
      keys.forEach(k => {
        const val = d[k as keyof CountryAnalyticsRow];
        point[k] = val != null ? Number(val) : undefined;
      });
      return point;
    });
};

export default function CountryDetailPage() {
  const router = useRouter();
  const { code } = useParams();
  const normalizedCode = (code as string).toUpperCase();
  const { data, isLoading, isError, error } = useCountryAnalytics(normalizedCode);

  if (isLoading) return <div className="p-6 space-y-4"><div className="h-8 w-48 bg-gray-200 rounded animate-pulse" /><div className="grid grid-cols-1 lg:grid-cols-3 gap-6"><div className="lg:col-span-2"><ChartSkeleton /></div><div className="lg:col-span-1"><CardSkeleton className="h-64" /></div></div></div>;
  if (isError) return <div className="p-6 bg-red-50 text-red-700 rounded border border-red-200">Error: {error?.message}</div>;
  if (!data || data.length === 0) return <div className="p-12 text-center bg-white rounded-md border border-gray-200">Không có dữ liệu cho quốc gia này.</div>;

  const displayName = `${normalizedCode}`;
  const latestData = data[data.length - 1];
  const firstYear = data[0]?.year;
  const lastYear = latestData?.year;

  const hasGrowth = data.some(d => d.actual_growth != null);
  const hasFiscal = data.some(d => d.actual_debt != null || d.actual_inflation != null);
  const hasSocial = data.some(d => d.actual_poverty != null || d.actual_unemployment != null);
  const hasRisk = data.some(d => d.actual_reer_deviation != null);

  const tabs: Array<{ id: string; label: string; status?: 'ok' | 'warning' | 'error'; content: React.ReactNode }> = [
    { id: 'growth', label: 'Tang truởng', status: hasGrowth ? 'ok' : undefined, content: <GrowthTab data={data} /> },
    { id: 'fiscal', label: 'Tài khóa & Tiền tệ?', status: hasFiscal ? 'ok' : 'warning', content: <FiscalMonetaryTab data={data} /> },
    { id: 'social', label: 'Xã hội', status: hasSocial ? 'ok' : 'warning', content: <SocialTab data={data} /> },
    { id: 'risk', label: 'Rủi ro', status: hasRisk ? 'ok' : 'error', content: <RiskTab data={data} /> },
  ];

  const contextItems: Array<{ icon: typeof BarChart3; label: string; value?: string; status?: 'ok' | 'warning' | 'error' }> = [
    { icon: BarChart3, label: 'Chu kì dữ liệu', value: `${firstYear} – ${lastYear}` },
    { icon: Activity, label: 'Tổng số quan sát', value: `${data.length} năm` },
    {
      icon: TrendingUp,
      label: 'Tăng trưởng mới nhất',
      value: latestData?.actual_growth != null ? `${latestData.actual_growth.toFixed(2)}%` : 'N/A',
      status: (latestData?.actual_growth != null && latestData.actual_growth > 0 ? 'ok' : 'warning') as 'ok' | 'warning'
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button onClick={() => router.push('/countries')} className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Quay lại danh sách
        </button>
      </div>

      <div className="bg-white rounded-md border border-gray-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Hồ sơ Kinh tế: {displayName}</h1>
          <p className="text-sm text-gray-500 mt-1">Dữ liệu vĩ mô tích hợp từ 5 bảng gold layer</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">
          <Download className="w-4 h-4" /> Xuất báo cáo
        </button>
      </div>

      <Tabs tabs={tabs} />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8">
          <div className="bg-white rounded-md border border-gray-200 p-6 min-h-[300px]">
            {tabs.find(t => t.id === 'growth')?.content || <EmptyChart indicator="Tăng trưởng GDP" />}
          </div>
        </div>
        <div className="lg:col-span-4">
          <ContextPanel title="Tóm tắt nhanh" items={contextItems} actions={[{ label: 'So sánh với cụm', onClick: () => router.push(`/compare?countries=${normalizedCode}&indicator=rGDP_growth_YoY`), variant: 'primary' }]} />
        </div>
      </div>
    </div>
  );
}

function GrowthTab({ data }: { data: CountryAnalyticsRow[] }) {
  const chartData = data.map(d => ({ year: d.year, actual: d.actual_growth, trend: d.trend_growth, isAnomaly: d.anomaly_growth != null && d.anomaly_growth >= 0.75 }));
  if (!data.some(d => d.actual_growth != null)) return <EmptyChart indicator="Tăng trưởng GDP thực tế" />;
  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Diễn biến Tăng trưởng GDP (%)</h3>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="year" stroke="#6b7280" fontSize={12} />
          <YAxis stroke="#6b7280" fontSize={12} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
          <Legend />
          <Line type="monotone" dataKey="actual" stroke="#3b82f6" name="Thực tế" dot={{ r: 3 }} />
          <Line type="monotone" dataKey="trend" stroke="#10b981" strokeDasharray="5 5" name="Xu hướng" dot={false} />
          {chartData.filter(d => d.isAnomaly).map((p) => (
            <ReferenceLine key={`growth-${p.year}`} x={p.year} stroke="#ef4444" strokeDasharray="3 3" />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function FiscalMonetaryTab({ data }: { data: CountryAnalyticsRow[] }) {
  if (!data.some(d => d.actual_debt != null || d.actual_inflation != null)) return <EmptyChart indicator="Nợ công & Lạm phát" />;
  const chartData = prepareChartData(data, ['actual_debt', 'actual_inflation']);
  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Nợ công (%GDP) & Lạm phát CPI (%)</h3>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="year" stroke="#6b7280" fontSize={12} />
          <YAxis stroke="#6b7280" fontSize={12} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
          <Legend />
          <Line type="monotone" dataKey="actual_debt" stroke="#f59e0b" name="Nợ công" dot={{ r: 3 }} />
          <Line type="monotone" dataKey="actual_inflation" stroke="#8b5cf6" name="Lạm phát CPI" dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function SocialTab({ data }: { data: CountryAnalyticsRow[] }) {
  if (!data.some(d => d.actual_poverty != null || d.actual_unemployment != null)) return <EmptyChart indicator="Nghèo đói & Thất nghiệp" />;
  const chartData = prepareChartData(data, ['actual_poverty', 'actual_unemployment']);
  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Tỷ lệ Nghèo (%) & Thất nghiệp (%)</h3>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="year" stroke="#6b7280" fontSize={12} />
          <YAxis stroke="#6b7280" fontSize={12} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
          <Legend />
          <Line type="monotone" dataKey="actual_poverty" stroke="#ef4444" name="Nghèo đói" dot={{ r: 3 }} />
          <Line type="monotone" dataKey="actual_unemployment" stroke="#06b6d4" name="Thất nghiệp" dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function RiskTab({ data }: { data: CountryAnalyticsRow[] }) {
  if (!data.some(d => d.actual_reer_deviation != null)) return <EmptyChart indicator="Lệch giá REER" />;
  const chartData = data.map(d => ({ year: d.year, reer: d.actual_reer_deviation, isAnomaly: d.anomaly_reer_deviation != null && d.anomaly_reer_deviation >= 0.75 }));
  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Lệch giá REER (%) & Cảnh báo</h3>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="year" stroke="#6b7280" fontSize={12} />
          <YAxis stroke="#6b7280" fontSize={12} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
          <Legend />
          <Line type="monotone" dataKey="reer" stroke="#dc2626" name="REER Deviation" dot={{ r: 3 }} />
          {chartData.filter(d => d.isAnomaly).map((p) => (
            <ReferenceLine key={`risk-${p.year}`} x={p.year} stroke="#dc2626" strokeDasharray="3 3" />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function EmptyChart({ indicator }: { indicator: string }) {
  return (
    <div className="h-[320px] flex flex-col items-center justify-center text-gray-500 bg-gray-50 rounded-md border border-dashed border-gray-300">
      <AlertTriangle className="w-8 h-8 text-gray-300 mb-3" />
      <p className="font-medium text-gray-700">Chưa có dữ liệu cho: {indicator}</p>
      <p className="text-xs mt-1">Pipeline analytics đang xử lý hoặc chỉ số không khả dụng.</p>
    </div>
  );
}