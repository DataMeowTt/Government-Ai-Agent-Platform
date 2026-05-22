'use client';
import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils/cn';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

interface Tab {
  id: string;
  label: string;
  content: React.ReactNode;
  status?: 'ok' | 'warning' | 'error';
}

interface TabsProps {
  tabs: Tab[];
  defaultActiveId?: string;
  onChange?: (id: string) => void;
}

const StatusIcon = ({ status, className }: { status?: Tab['status']; className?: string }) => {
  if (status === 'ok') return <CheckCircle2 className={cn('w-4 h-4 text-emerald-500', className)} />;
  if (status === 'warning') return <AlertTriangle className={cn('w-4 h-4 text-amber-500', className)} />;
  if (status === 'error') return <XCircle className={cn('w-4 h-4 text-rose-500', className)} />;
  return null;
};

export default function Tabs({ tabs, defaultActiveId, onChange }: TabsProps) {
  const [activeId, setActiveId] = useState(defaultActiveId || tabs[0]?.id || '');

  useEffect(() => {
    if (defaultActiveId && defaultActiveId !== activeId) {
      setActiveId(defaultActiveId);
    }
  }, [defaultActiveId]);

  const activeTab = tabs.find(t => t.id === activeId) || tabs[0];

  const handleTabChange = (id: string) => {
    setActiveId(id);
    onChange?.(id);
  };

  return (
    <div>
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-6 overflow-x-auto pb-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={cn(
                'py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
                tab.id === activeId
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              {tab.label}
              <StatusIcon status={tab.status} />
            </button>
          ))}
        </nav>
      </div>
      <div key={activeId} className="min-h-[300px] transition-all duration-200">
        {activeTab?.content}
      </div>
    </div>
  );
}