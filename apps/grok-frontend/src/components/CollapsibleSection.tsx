import { useState, type ReactNode } from 'react';
import { cn } from '../utils/cn';

interface Props {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  badge?: string;
}

export default function CollapsibleSection({ title, subtitle, defaultOpen = false, children, badge }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-zinc-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-zinc-800">{title}</span>
          {badge ? (
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600">
              {badge}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {subtitle ? <span className="hidden text-xs text-zinc-400 sm:inline">{subtitle}</span> : null}
          <svg
            className={cn('h-4 w-4 shrink-0 text-zinc-400 transition-transform', open && 'rotate-180')}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </div>
      </button>
      {open ? <div className="border-t border-zinc-100 px-4 py-4">{children}</div> : null}
    </div>
  );
}
