import { RATIO_OPTIONS } from '../lib/constants';
import type { Ratio } from '../lib/types';
import { cn } from '../utils/cn';

interface Props {
  value: Ratio;
  onChange: (ratio: Ratio) => void;
}

function RatioPreview({ ratio, active }: { ratio: Ratio; active: boolean }) {
  const map: Record<Ratio, string> = {
    '16:9': 'w-7 h-4',
    '9:16': 'w-4 h-7',
    '1:1': 'w-5 h-5',
    '4:3': 'w-6 h-[18px]',
    '3:4': 'w-[18px] h-6',
  };
  return (
    <span
      className={cn(
        'flex items-center justify-center rounded-sm border',
        map[ratio],
        active ? 'border-indigo-500 bg-indigo-500/10' : 'border-zinc-300 bg-zinc-100',
      )}
    />
  );
}

export default function RatioSelector({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {RATIO_OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <label
            key={opt.value}
            className={cn(
              'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition',
              active ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500' : 'border-zinc-200 hover:border-zinc-300',
            )}
          >
            <input
              type="checkbox"
              checked={active}
              onChange={() => onChange(opt.value)}
              className="sr-only"
            />
            <RatioPreview ratio={opt.value} active={active} />
            <span className="flex flex-col">
              <span className="text-sm font-semibold text-zinc-800">
                {opt.label}
                {opt.value === '9:16' ? (
                  <span className="ml-1 text-[10px] font-normal text-indigo-500">（默认）</span>
                ) : null}
              </span>
              <span className="text-[11px] text-zinc-400">{opt.desc}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
