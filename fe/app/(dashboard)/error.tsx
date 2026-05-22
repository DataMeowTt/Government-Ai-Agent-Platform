'use client';
import { useEffect } from 'react';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Dashboard error:', error);
  }, [error]);

  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-6">
      <h2 className="text-lg font-semibold text-red-800">Đã xảy ra lỗi khi tải trang</h2>
      <p className="mt-2 text-sm text-red-700">{error.message}</p>
      <button
        onClick={reset}
        className="mt-4 rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100"
      >
        Thử lại
      </button>
    </div>
  );
}
