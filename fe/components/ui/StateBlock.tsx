import { AlertCircle, Info, Loader2 } from 'lucide-react';

interface StateBlockProps {
  mode: 'loading' | 'empty' | 'error';
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export default function StateBlock({ mode, title, description, action }: StateBlockProps) {
  const icon =
    mode === 'loading' ? (
      <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
    ) : mode === 'error' ? (
      <AlertCircle className="h-5 w-5 text-red-600" />
    ) : (
      <Info className="h-5 w-5 text-slate-500" />
    );

  return (
    <div className="rounded-md border border-slate-200 bg-white px-5 py-8 text-center shadow-sm">
      <div className="mb-3 flex justify-center">{icon}</div>
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      {description ? <p className="mx-auto mt-2 max-w-xl text-sm text-slate-600">{description}</p> : null}
      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-4 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          {action.label}
        </button>
      ) : null}
    </div>
  );
}
