'use client';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import PageHeader from '@/components/ui/PageHeader';
import FilterBar from '@/components/ui/FilterBar';
import StateBlock from '@/components/ui/StateBlock';
import Pagination from '@/components/ui/Pagination';
import { TableSkeleton } from '@/components/ui/Skeletons';
import AnomaliesTable from '@/components/tables/AnomaliesTable';
import { useAnomalies } from '@/lib/hooks/useAnomalies';
import { useCountries } from '@/lib/hooks/useCountries';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { useUrlState } from '@/lib/hooks/useUrlState';

const PAGE_SIZE = 12;

export default function AnomaliesPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} />}>
      <AnomaliesPageContent />
    </Suspense>
  );
}

function AnomaliesPageContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [country, setCountry] = useUrlState<string>('country', '');
  const [indicator, setIndicator] = useUrlState<string>('indicator', '');
  const [threshold, setThreshold] = useUrlState<number>('threshold', 0.75);
  const [page, setPage] = useUrlState<number>('page', 1);

  const [draftThreshold, setDraftThreshold] = useState<number>(threshold);
  const [draftCountry, setDraftCountry] = useState<string>(country);
  const [draftIndicator, setDraftIndicator] = useState<string>(indicator);

  const countriesQuery = useCountries();
  const indicatorsQuery = useIndicators();
  const { data, total, isLoading, isError, error, isEmpty } = useAnomalies({
    country: country || undefined,
    indicator: indicator || undefined,
    threshold,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / PAGE_SIZE)), [total]);

  useEffect(() => {
    setDraftCountry(country);
    setDraftIndicator(indicator);
    setDraftThreshold(threshold);
  }, [country, indicator, threshold]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages, setPage]);

  const replaceUrlState = (nextCountry: string, nextIndicator: string, nextThreshold: number, nextPage: number) => {
    const params = new URLSearchParams(searchParams.toString());
    if (nextCountry) params.set('country', nextCountry);
    else params.delete('country');
    if (nextIndicator) params.set('indicator', nextIndicator);
    else params.delete('indicator');
    if (nextThreshold !== 0.75) params.set('threshold', String(nextThreshold));
    else params.delete('threshold');
    if (nextPage > 1) params.set('page', String(nextPage));
    else params.delete('page');
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    window.setTimeout(() => {
      window.history.replaceState(null, '', nextUrl);
    }, 0);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Bất thường dữ liệu kinh tế"
        description="Theo dõi các điểm dữ liệu có điểm bất thường thống kê cao theo ngưỡng lọc."
        actions={<p className="text-sm text-slate-600">Tổng kết quả: {total}</p>}
      />

      <FilterBar>
        <div className="md:col-span-4">
          <label className="mb-1 block text-sm font-medium text-slate-700">Quốc gia</label>
          <select
            value={draftCountry}
            onChange={(event) => setDraftCountry(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            <option value="">Tất cả quốc gia</option>
            {(countriesQuery.data || []).map((item) => (
              <option key={item.country_code} value={item.country_code}>
                {item.country_name} ({item.country_code})
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-4">
          <label className="mb-1 block text-sm font-medium text-slate-700">Chỉ số</label>
          <select
            value={draftIndicator}
            onChange={(event) => setDraftIndicator(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            <option value="">Tất cả chỉ số</option>
            {(indicatorsQuery.data || [])
              .filter((item) => item.supports_anomaly !== false)
              .map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name} ({item.code})
                </option>
              ))}
          </select>
        </div>
        <div className="md:col-span-3">
          <div className="mb-1 flex items-center justify-between">
            <label className="block text-sm font-medium text-slate-700">Ngưỡng điểm bất thường thống kê</label>
            <span className="text-xs text-slate-500">{draftThreshold.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0.5}
            max={1}
            step={0.01}
            value={draftThreshold}
            onChange={(event) => setDraftThreshold(Number(event.target.value))}
            className="h-2 w-full cursor-pointer accent-slate-700"
          />
        </div>
        <div className="md:col-span-1 flex items-end gap-2">
          <button
            type="button"
            onClick={() => {
              setPage(1);
              setCountry(draftCountry);
              setIndicator(draftIndicator);
              setThreshold(draftThreshold);
              replaceUrlState(draftCountry, draftIndicator, draftThreshold, 1);
            }}
            className="h-10 w-full rounded-md bg-slate-800 text-sm font-medium text-white hover:bg-slate-900"
          >
            Áp dụng
          </button>
          <button
            type="button"
            onClick={() => {
              setPage(1);
              setCountry('');
              setIndicator('');
              setThreshold(0.75);
              setDraftCountry('');
              setDraftIndicator('');
              setDraftThreshold(0.75);
              replaceUrlState('', '', 0.75, 1);
            }}
            className="h-10 w-full rounded-md border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Đặt lại
          </button>
        </div>
      </FilterBar>

      <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        Điểm bất thường thống kê càng cao càng thể hiện mức lệch lớn so với xu hướng dữ liệu lịch sử. Điểm cao không tự
        động có nghĩa là dữ liệu sai, mà là tín hiệu cần phân tích thêm.
      </div>

      {isLoading ? <TableSkeleton rows={8} /> : null}

      {isError ? (
        <StateBlock
          mode="error"
          title="Không tải được dữ liệu bất thường"
          description={error instanceof Error ? error.message : 'Lỗi không xác định khi tải dữ liệu bất thường.'}
        />
      ) : null}

      {!isLoading && !isError && isEmpty ? (
        <StateBlock
          mode="empty"
          title="Không có bản ghi bất thường theo bộ lọc hiện tại"
          description="Hãy giảm ngưỡng hoặc bỏ lọc quốc gia/chỉ số để mở rộng kết quả."
          action={{
            label: 'Đặt lại bộ lọc',
            onClick: () => {
              setPage(1);
              setCountry('');
              setIndicator('');
              setThreshold(0.75);
              setDraftCountry('');
              setDraftIndicator('');
              setDraftThreshold(0.75);
            },
          }}
        />
      ) : null}

      {!isLoading && !isError && !isEmpty ? (
        <>
          <AnomaliesTable data={data || []} />
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={setPage}
            totalItems={total}
            itemsPerPage={PAGE_SIZE}
          />
        </>
      ) : null}
    </div>
  );
}
