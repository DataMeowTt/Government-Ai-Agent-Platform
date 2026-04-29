'use client';
interface Props { currentPage: number; totalPages: number; onPageChange: (page: number) => void; }

export default function Pagination({ currentPage, totalPages, onPageChange }: Props) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex gap-2 justify-center items-center mt-4">
      <button disabled={currentPage === 1} onClick={() => onPageChange(currentPage - 1)}
        className="px-3 py-1 border rounded bg-white hover:bg-gray-50 disabled:opacity-40">Trước</button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).slice(0, 5).map(p => (
        <button key={p} onClick={() => onPageChange(p)}
          className={`px-3 py-1 border rounded ${p === currentPage ? 'bg-blue-600 text-white' : 'bg-white hover:bg-gray-50'}`}>
          {p}
        </button>
      ))}
      <button disabled={currentPage === totalPages} onClick={() => onPageChange(currentPage + 1)}
        className="px-3 py-1 border rounded bg-white hover:bg-gray-50 disabled:opacity-40">Sau</button>
    </div>
  );
}