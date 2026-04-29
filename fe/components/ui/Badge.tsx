import { getAnomalyColor } from '@/lib/utils/format';

export default function AnomalyBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="px-2 py-1 bg-gray-100 text-gray-500 rounded text-xs">N/A</span>;
  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${getAnomalyColor(score)}`}>
      {score.toFixed(3)}
    </span>
  );
}