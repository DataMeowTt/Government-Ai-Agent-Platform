'use client';
import { useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  siblingsCount?: number;
  totalItems?: number;
  itemsPerPage?: number;
}

export default function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  siblingsCount = 1,
  totalItems,
  itemsPerPage = 8,
}: PaginationProps) {
  const safeCurrent = Math.min(Math.max(currentPage, 1), totalPages);

  const paginationRange = useMemo(() => {
    const totalNumbers = siblingsCount * 2 + 5;
    if (totalNumbers >= totalPages) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }

    const leftSibling = Math.max(safeCurrent - siblingsCount, 1);
    const rightSibling = Math.min(safeCurrent + siblingsCount, totalPages);
    const showLeftDots = leftSibling > 2;
    const showRightDots = rightSibling < totalPages - 2;

    if (!showLeftDots && showRightDots) {
      const rightItemCount = 3 + siblingsCount * 2;
      return [...Array.from({ length: rightItemCount }, (_, i) => i + 1), '...', totalPages];
    }

    if (showLeftDots && !showRightDots) {
      const leftItemCount = 3 + siblingsCount * 2;
      return [1, '...', ...Array.from({ length: leftItemCount }, (_, i) => totalPages - leftItemCount + i + 1)];
    }

    return [
      1,
      '...',
      ...Array.from({ length: siblingsCount * 2 + 3 }, (_, i) => leftSibling + i),
      '...',
      totalPages,
    ];
  }, [safeCurrent, totalPages, siblingsCount]);

  if (totalPages <= 1) return null;

  const computedTotalItems =
    typeof totalItems === 'number' && totalItems >= 0 ? totalItems : totalPages * itemsPerPage;
  const start = computedTotalItems === 0 ? 0 : (safeCurrent - 1) * itemsPerPage + 1;
  const end = Math.min(safeCurrent * itemsPerPage, computedTotalItems);

  const handlePageChange = (page: number | string) => {
    if (typeof page !== 'number') return;
    const nextPage = Math.min(Math.max(page, 1), totalPages);
    onPageChange(nextPage);
  };

  return (
    <div className="mt-4 flex items-center justify-between rounded-md border border-slate-200 bg-white px-4 py-3">
      <span className="text-sm text-slate-600">{`Hiển thị ${start}–${end} / ${computedTotalItems}`}</span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={safeCurrent === 1}
          onClick={() => handlePageChange(safeCurrent - 1)}
          className="rounded border border-slate-300 p-2 hover:bg-slate-50 disabled:opacity-50"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        {paginationRange.map((page, idx) =>
          page === '...' ? (
            <span key={`dot-${idx}`} className="px-2 text-slate-500">
              ...
            </span>
          ) : (
            <button
              type="button"
              key={`page-${page}-${idx}`}
              onClick={() => handlePageChange(page as number)}
              className={`h-8 rounded border px-3 text-sm ${
                page === safeCurrent
                  ? 'border-slate-800 bg-slate-800 text-white'
                  : 'border-slate-300 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {page}
            </button>
          )
        )}

        <button
          type="button"
          disabled={safeCurrent === totalPages}
          onClick={() => handlePageChange(safeCurrent + 1)}
          className="rounded border border-slate-300 p-2 hover:bg-slate-50 disabled:opacity-50"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
