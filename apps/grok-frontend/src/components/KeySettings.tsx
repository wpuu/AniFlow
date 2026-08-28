import { useState } from 'react';

interface Props {
  keyCount: number;
  apiKeys: string[];
  busyKeyIndexes?: Set<number>;
  onKeyCountChange: (count: number) => void;
  onKeyChange: (index: number, value: string) => void;
}

const MAX_KEYS = 9;

export default function KeySettings({
  keyCount,
  apiKeys,
  busyKeyIndexes = new Set<number>(),
  onKeyCountChange,
  onKeyChange,
}: Props) {
  const [visible, setVisible] = useState<Record<number, boolean>>({});

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-zinc-600">Key 数量</label>
        <input
          type="number"
          min={1}
          max={MAX_KEYS}
          value={keyCount}
          onChange={(e) => {
            const v = Math.min(MAX_KEYS, Math.max(1, Number(e.target.value) || 1));
            onKeyCountChange(v);
          }}
          className="w-20 rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-indigo-500"
        />
        <span className="text-xs text-zinc-400">
          支持 1-{MAX_KEYS} 个 Key，数量越多可同时并行生成的视频越多。
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {Array.from({ length: keyCount }).map((_, i) => {
          const busy = busyKeyIndexes.has(i);
          return (
            <div
              key={i}
              className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50/60 px-3 py-2"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold text-white">
                {i + 1}
              </span>
              <input
                type={visible[i] ? 'text' : 'password'}
                value={apiKeys[i] ?? ''}
                disabled={busy}
                onChange={(e) => onKeyChange(i, e.target.value)}
                placeholder={`请输入 Key ${i + 1}（API Key）`}
                title={busy ? '该 Key 有任务正在运行，完成或停止跟踪后才能修改' : undefined}
                className="min-w-0 flex-1 border-none bg-transparent text-sm outline-none placeholder:text-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
              />
              {busy ? (
                <span className="shrink-0 text-[10px] font-medium text-amber-600">运行中锁定</span>
              ) : (
                <button
                  type="button"
                  onClick={() => setVisible((v) => ({ ...v, [i]: !v[i] }))}
                  className="shrink-0 text-xs text-zinc-400 hover:text-indigo-600"
                >
                  {visible[i] ? '隐藏' : '显示'}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
