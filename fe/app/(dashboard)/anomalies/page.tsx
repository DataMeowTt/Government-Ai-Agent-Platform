'use client';

import { Suspense, useMemo, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
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
  const [country, setCountry] = useUrlState<string>('country', '');
  const [indicator, setIndicator] = useUrlState<string>('indicator', '');
  const [threshold, setThreshold] = useUrlState<number>('threshold', 0.75);
  const [page, setPage] = useUrlState<number>('page', 1);

  const [draftThreshold, setDraftThreshold] = useState<number>(threshold);
  const [draftCountry, setDraftCountry] = useState<string>(country);
  const [draftIndicator, setDraftIndicator] = useState<string>(indicator);

  const countriesQuery = useCountries();
  const indicatorsQuery = useIndicators();
  const { data, total, isLoading, isFetching, isError, error, isEmpty } = useAnomalies({
    country: country || undefined,
    indicator: indicator || undefined,
    threshold,
    limit: PAGE_SIZE,
    offset: (Math.max(page, 1) - 1) * PAGE_SIZE,
  });

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / PAGE_SIZE)), [total]);
  const safePage = Math.min(Math.max(page, 1), totalPages);

  const anomalyIndicators = useMemo(() => {
    const indicators = (indicatorsQuery.data || []).filter(item => item.supports_anomaly === true);
    return indicators.length > 0
      ? indicators
      : [
          { code: 'rGDP_growth_YoY', name: 'Tăng trưởng GDP thực' },
          { code: 'govdebt_GDP', name: 'Nợ công/GDP' },
          { code: 'REER_deviation', name: 'Độ lệch REER' },
        ];
  }, [indicatorsQuery.data]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Bất thường dữ liệu kinh tế"
        description="Theo dõi các điểm dữ liệu có điểm bất thường thống kê cao theo ngưỡng lọc."
        actions={
          <p className="inline-flex items-center gap-2 text-sm text-slate-600">
            <AlertTriangle className="h-4 w-4" />
            Tổng kết quả: {total}
          </p>
        }
      />

      <FilterBar>
        <div className="md:col-span-4">
          <label htmlFor="anomaly-country" className="mb-1 block text-sm font-medium text-slate-700">
            Quốc gia
          </label>
          <select
            id="anomaly-country"
            name="country"
            value={draftCountry}
            onChange={event => setDraftCountry(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            <option value="">Tất cả quốc gia</option>
            {(countriesQuery.data || []).map(item => (
              <option key={item.country_code} value={item.country_code}>
                {item.country_name} ({item.country_code})
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-4">
          <label htmlFor="anomaly-indicator" className="mb-1 block text-sm font-medium text-slate-700">
            Chỉ số
          </label>
          <select
            id="anomaly-indicator"
            name="indicator"
            value={draftIndicator}
            onChange={event => setDraftIndicator(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            <option value="">Tất cả chỉ số</option>
            {anomalyIndicators.map(item => (
              <option key={item.code} value={item.code}>
                {item.name} ({item.code})
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-4">
          <div className="mb-1 flex items-center justify-between">
            <label htmlFor="anomaly-threshold" className="block text-sm font-medium text-slate-700">
              Ngưỡng điểm bất thường thống kê
            </label>
            <span className="text-xs text-slate-500">{draftThreshold.toFixed(2)}</span>
          </div>
          <input
            id="anomaly-threshold"
            name="threshold"
            type="range"
            min={0.5}
            max={1}
            step={0.01}
            value={draftThreshold}
            onChange={event => setDraftThreshold(Number(event.target.value))}
            className="h-2 w-full cursor-pointer accent-slate-700"
          />
        </div>

        <div className="md:col-span-12 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:max-w-md">
          <button
            type="button"
            onClick={() => {
              setPage(1);
              setCountry(draftCountry);
              setIndicator(draftIndicator);
              setThreshold(draftThreshold);
            }}
            className="min-h-10 w-full rounded-md bg-slate-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-900"
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
            }}
            className="min-h-10 w-full rounded-md border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Đặt lại
          </button>
        </div>
      </FilterBar>

      <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        Điểm bất thường thống kê càng cao càng thể hiện mức lệch lớn so với xu hướng dữ liệu lịch sử.
      </div>

      {isLoading ? <TableSkeleton rows={8} /> : null}

      {isError ? (
        <StateBlock
          mode="error"
          title="Không tải được dữ liệu bất thường"
          description={
            error instanceof Error
              ? error.message
              : 'Lỗi không xác định khi tải dữ liệu bất thường.'
          }
        />
      ) : null}

      {!isLoading && !isError && isEmpty ? (
        <StateBlock
          mode="empty"
          title="Không có bản ghi bất thường theo bộ lọc hiện tại"
          description="Hãy giảm ngưỡng hoặc bỏ lọc quốc gia/chỉ số để mở rộng kết quả."
        />
      ) : null}

      {!isLoading && !isError && !isEmpty ? (
        <>
          <div className="relative">
            <AnomaliesTable data={data || []} />
            {isFetching ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md bg-white/70 backdrop-blur-[1px]">
                <div className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading...
                </div>
              </div>
            ) : null}
          </div>
          <Pagination
            currentPage={safePage}
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
