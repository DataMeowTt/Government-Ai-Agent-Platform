'use client';
import Link from 'next/link';
import { Bot, Globe2, Layers, ListChecks } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import SectionCard from '@/components/ui/SectionCard';
import StatCard from '@/components/ui/StatCard';
import StateBlock from '@/components/ui/StateBlock';
import { useCountries } from '@/lib/hooks/useCountries';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { useClusters } from '@/lib/hooks/useClusters';

function MetricErrorCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-4 py-4">
      <p className="text-sm font-semibold text-red-700">{title}</p>
      <p className="mt-1 text-xs text-red-600">{message}</p>
    </div>
  );
}

const SOURCES = [
  {
    name: 'World Bank WDI',
    href: 'https://wdi.worldbank.org/',
    description: 'Bộ dữ liệu phát triển toàn cầu về tăng trưởng, tài khóa, xã hội và các chỉ số kinh tế vĩ mô.',
  },
  {
    name: 'FAOSTAT',
    href: 'https://www.fao.org/faostat/',
    description: 'Cơ sở dữ liệu thống kê của FAO về nông nghiệp, lương thực và các chỉ số liên quan.',
  },
  {
    name: 'Global Macro Database',
    href: 'https://www.globalmacrodata.com/',
    description: 'Cơ sở dữ liệu kinh tế vĩ mô quốc tế theo quốc gia và theo thời gian.',
  },
];

export default function DashboardPage() {
  const countriesQuery = useCountries();
  const indicatorsQuery = useIndicators();
  const clustersQuery = useClusters(2025);

  const clusterCount = clustersQuery.data ? new Set(clustersQuery.data.map((item) => item.cluster_id)).size : 0;
  const latestClusterYear =
    clustersQuery.data && clustersQuery.data.length > 0
      ? Math.max(...clustersQuery.data.map((item) => item.latest_valid_year ?? item.year))
      : null;

  const updateYearText = latestClusterYear
    ? `Dữ liệu cập nhật đến năm ${latestClusterYear}`
    : 'Thời điểm cập nhật hệ thống: chưa có thông tin công bố';

  return (
    <div className="space-y-6">
      <PageHeader
        title="Nền tảng phân tích dữ liệu kinh tế công"
        description="Cổng thông tin hỗ trợ theo dõi, so sánh và diễn giải các chỉ số kinh tế vĩ mô theo quốc gia."
      />

      <SectionCard title="Phạm vi hệ thống">
        <p className="text-sm leading-6 text-slate-700">
          Hệ thống tổng hợp dữ liệu kinh tế công khai theo quốc gia, phục vụ theo dõi xu hướng tăng trưởng, tài khóa,
          tiền tệ, rủi ro và phúc lợi xã hội. Người dùng có thể tra cứu hồ sơ quốc gia, so sánh theo thời gian, nhận diện
          điểm bất thường thống kê và sử dụng trợ lý dữ liệu để diễn giải kết quả.
        </p>
      </SectionCard>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        {countriesQuery.isError ? (
          <MetricErrorCard title="Tổng số quốc gia" message="Không tải được dữ liệu quốc gia." />
        ) : (
          <StatCard
            label="Tổng số quốc gia"
            value={countriesQuery.isLoading ? '...' : String(countriesQuery.data?.length ?? 0)}
            note="Số quốc gia có dữ liệu trong hệ thống"
            icon={<Globe2 className="h-5 w-5" />}
          />
        )}
        {indicatorsQuery.isError ? (
          <MetricErrorCard title="Tổng số chỉ số" message="Không tải được danh mục chỉ số." />
        ) : (
          <StatCard
            label="Tổng số chỉ số"
            value={indicatorsQuery.isLoading ? '...' : String(indicatorsQuery.data?.length ?? 0)}
            note="Danh mục chỉ số đang hỗ trợ"
            icon={<ListChecks className="h-5 w-5" />}
          />
        )}
        <StatCard
          label="Năm dữ liệu gần nhất"
          value={latestClusterYear ? String(latestClusterYear) : 'Chưa rõ'}
          note={updateYearText}
          icon={<Layers className="h-5 w-5" />}
        />
        {clustersQuery.isError ? (
          <MetricErrorCard title="Số cụm khả dụng" message="Không tải được danh sách cụm." />
        ) : (
          <StatCard
            label="Số cụm khả dụng"
            value={clustersQuery.isLoading ? '...' : String(clusterCount)}
            note={latestClusterYear ? `Năm cụm khả dụng: ${latestClusterYear}` : 'Chưa xác định năm cụm khả dụng'}
            icon={<Bot className="h-5 w-5" />}
          />
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard title="Nhóm chỉ số chính">
          <ul className="space-y-2 text-sm text-slate-700">
            <li>Tăng trưởng và quy mô nền kinh tế(growth_dynamics)</li>
            <li>Tài khóa và tiền tệ(fiscal_monetary)</li>
            <li>Rủi ro khủng hoảng và ổn định vĩ mô(crisis_risk)</li>
            <li>Phúc lợi xã hội và thị trường lao động(social_welfare)</li>
            <li>Cơ cấu kinh tế và chuyển dịch ngành(structural_composition)</li>
          </ul>
        </SectionCard>
        <SectionCard title="Năng lực phân tích">
          <ul className="space-y-2 text-sm text-slate-700">
            <li>Hồ sơ kinh tế quốc gia theo chuỗi thời gian.</li>
            <li>So sánh một chỉ số giữa nhiều quốc gia theo cùng giai đoạn.</li>
            <li>Phân nhóm cấu trúc kinh tế để tìm quốc gia tương đồng.</li>
            <li>Phát hiện bất thường thống kê theo ngưỡng giám sát.</li>
            <li>Trợ lý dữ liệu AI hỗ trợ diễn giải kết quả phân tích.</li>
          </ul>
        </SectionCard>
      </section>

      <SectionCard title="Nguồn dữ liệu">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {SOURCES.map((source) => (
            <article key={source.name} className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-900">{source.name}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-700">{source.description}</p>
              <a
                href={source.href}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex text-sm font-medium text-slate-800 underline underline-offset-4"
              >
                Xem nguồn dữ liệu gốc
              </a>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Mục đích từng trang">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <Link href="/countries" className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:bg-slate-50">
            <strong>Quốc gia:</strong> Tra cứu danh sách và mở hồ sơ kinh tế theo từng quốc gia.
          </Link>
          <Link href="/compare" className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:bg-slate-50">
            <strong>So sánh:</strong> So sánh một chỉ số giữa nhiều quốc gia theo thời gian.
          </Link>
          <Link href="/clusters?year=2025" className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:bg-slate-50">
            <strong>Nhóm cấu trúc:</strong> Xem các quốc gia có cấu trúc kinh tế tương đồng trong cùng năm phân tích.
          </Link>
          <Link href="/anomalies" className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:bg-slate-50">
            <strong>Bất thường:</strong> Theo dõi các điểm dữ liệu lệch mạnh so với xu hướng lịch sử.
          </Link>
          <Link href="/indicators" className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:bg-slate-50">
            <strong>Chỉ số:</strong> Xem danh mục, đơn vị và khả năng phân tích của từng chỉ số.
          </Link>
          <Link href="/chat" className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:bg-slate-50">
            <strong>Trợ lý dữ liệu:</strong> Đặt câu hỏi phân tích và nhận kết quả diễn giải kèm bảng, biểu đồ.
          </Link>
        </div>
      </SectionCard>

      {!countriesQuery.isLoading &&
      !indicatorsQuery.isLoading &&
      !clustersQuery.isLoading &&
      (countriesQuery.data?.length ?? 0) === 0 &&
      (indicatorsQuery.data?.length ?? 0) === 0 &&
      (clustersQuery.data?.length ?? 0) === 0 ? (
        <StateBlock
          mode="empty"
          title="Chưa có dữ liệu tổng quan"
          description="Hiện chưa tải được dữ liệu cho trang tổng quan. Vui lòng thử lại sau."
        />
      ) : null}
    </div>
  );
}
