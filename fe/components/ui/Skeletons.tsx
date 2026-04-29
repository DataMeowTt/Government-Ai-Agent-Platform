export const TableSkeleton = ({ rows = 5 }: { rows?: number }) => (
  <div className="animate-pulse space-y-3">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="h-10 bg-gray-200 rounded" />
    ))}
  </div>
);

export const CardSkeleton = () => (
  <div className="animate-pulse bg-gray-200 h-24 rounded-lg" />
);

export const ChartSkeleton = () => (
  <div className="animate-pulse bg-gray-200 h-64 rounded-lg" />
);