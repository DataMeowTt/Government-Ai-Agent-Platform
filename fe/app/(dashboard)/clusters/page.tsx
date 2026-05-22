'use client';
import { Suspense, useMemo } from 'react';
import Link from 'next/link';
import { Layers } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import FilterBar from '@/components/ui/FilterBar';
import SectionCard from '@/components/ui/SectionCard';
import StatCard from '@/components/ui/StatCard';
import StateBlock from '@/components/ui/StateBlock';
import { CardSkeleton } from '@/components/ui/Skeletons';
import { useUrlState } from '@/lib/hooks/useUrlState';
import { useClusters } from '@/lib/hooks/useClusters';

const YEAR_OPTIONS = [2000, 2010, 2020, 2025];

export default function ClustersPage() {
  return (
    <Suspense fallback={<CardSkeleton className="h-48" />}>
      <ClustersPageContent />
    </Suspense>
  );
}

function ClustersPageContent() {
  const [year, setYear] = useUrlState<number>('year', 2025);
  const { data, isLoading, isError, error } = useClusters(year);
  const clusters = data || [];

  const grouped = useMemo(() => {
    const map = new Map<number, { clusterId: number; countries: { code: string; name: string }[] }>();
    clusters.forEach((item) => {
      if (!map.has(item.cluster_id)) {
        map.set(item.cluster_id, { clusterId: item.cluster_id, countries: [] });
      }
      map.get(item.cluster_id)!.countries.push({
        code: item.country_code,
        name: item.country || item.country_code,
      });
    });
    return Array.from(map.values()).sort((a, b) => a.clusterId - b.clusterId);
  }, [clusters]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Nhóm cấu trúc kinh tế"
        description="Phân nhóm quốc gia theo mức độ tương đồng về cấu trúc kinh tế trong cùng năm phân tích."
      />

      <FilterBar>
        <div className="md:col-span-3">
          <label className="mb-1 block text-sm font-medium text-slate-700">Năm dữ liệu</label>
          <select
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {YEAR_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </FilterBar>

      {isLoading ? <CardSkeleton className="h-40" /> : null}

      {isError ? (
        <StateBlock
          mode="error"
          title="Không tải được dữ liệu nhóm cấu trúc"
          description={error instanceof Error ? error.message : 'Lỗi không xác định khi tải dữ liệu nhóm cấu trúc.'}
        />
      ) : null}

      {!isLoading && !isError && grouped.length === 0 ? (
        <StateBlock
          mode="empty"
          title={`Không có dữ liệu nhóm cấu trúc cho năm ${year}`}
          description="Hãy thử chọn một năm khác trong danh sách 2000, 2010, 2020, 2025."
        />
      ) : null}

      {!isLoading && !isError && grouped.length > 0 ? (
        <>
          <SectionCard title="Hiểu về nhóm cấu trúc kinh tế">
            <div className="space-y-2 text-sm text-slate-700">
              <p>
                Nhóm cấu trúc kinh tế giúp nhận diện các quốc gia có đặc điểm kinh tế tương đồng trong cùng một năm phân
                tích, từ đó hỗ trợ so sánh theo bối cảnh phù hợp hơn.
              </p>
              <p>
                Cụm không phải xếp hạng tốt hoặc xấu; đây là nhóm quốc gia có cấu trúc kinh tế tương đồng trong cùng năm
                phân tích.
              </p>
              <p>Hồ sơ diễn giải chi tiết cụm sẽ được bổ sung khi có dữ liệu mô tả cụm.</p>
            </div>
          </SectionCard>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <StatCard label="Năm đang xem" value={String(year)} icon={<Layers className="h-5 w-5" />} />
            <StatCard label="Số cụm" value={String(grouped.length)} />
            <StatCard label="Số quốc gia" value={String(clusters.length)} />
          </section>

          <SectionCard title="Danh sách cụm">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {grouped.map((cluster) => (
                <article key={cluster.clusterId} className="rounded-md border border-slate-200 bg-slate-50 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">Cụm {cluster.clusterId}</h3>
                    <span className="rounded border border-slate-300 bg-white px-2 py-0.5 text-xs text-slate-600">
                      {cluster.countries.length} quốc gia
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {cluster.countries.map((country) => (
                      <Link
                        key={`${cluster.clusterId}-${country.code}`}
                        href={`/countries/${country.code}`}
                        className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                      >
                        {country.name} ({country.code})
                      </Link>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
