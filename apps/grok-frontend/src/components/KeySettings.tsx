import { useState } from 'react';
import type { AgnesApiDomain } from '../lib/types';

interface Props {
  keyCount: number;
  apiKeys: string[];
  apiDomains: AgnesApiDomain[];
  busyKeyIndexes?: Set<number>;
  onKeyCountChange: (count: number) => void;
  onKeyChange: (index: number, value: string) => void;
  onDomainChange: (index: number, value: AgnesApiDomain) => void;
}
const MAX_KEYS = 9;
export default function KeySettings({
  keyCount, apiKeys, apiDomains, busyKeyIndexes = new Set<number>(),
  onKeyCountChange, onKeyChange, onDomainChange,
}: Props) {
  const [visible, setVisible] = useState<Record<number, boolean>>({});
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-zinc-600">Key 数量</label>
        <input type="number" min={1} max={MAX_KEYS} value={keyCount}
          onChange={(e) => onKeyCountChange(Math.min(MAX_KEYS, Math.max(1, Number(e.target.value) || 1)))}
          className="w-20 rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-indigo-500" />
        <span className="text-xs text-zinc-400">支持1–9个Key，正在生成的不参与新批次。每条Key可指定注册站点，默认国际站。</span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {Array.from({ length: keyCount }).map((_, i) => {
          const busy = busyKeyIndexes.has(i);
          return (
            <div key={i} className="flex min-w-0 items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50/60 px-2 py-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold text-white">{i + 1}</span>
              <input type={visible[i] ? 'text' : 'password'} value={apiKeys[i] ?? ''} disabled={busy}
                onChange={(e) => onKeyChange(i, e.target.value)}
                placeholder={`请输入 Key ${i + 1}（API Key）`}
                title={busy ? '有任务正在生成；暂时锁定该密钥' : undefined}
                className="min-w-0 flex-1 border-none bg-transparent text-xs outline-none placeholder:text-zinc-400 disabled:cursor-not-allowed disabled:opacity-50" />
              <select aria-label={`Key ${i + 1} API域名`} value={apiDomains[i] ?? 'global'} disabled={busy}
                onChange={(e) => onDomainChange(i, e.target.value as AgnesApiDomain)}
                title="Key所属站点：国际站 / 中国站 / 官方备用站（不自动试错）"
                className="w-[72px] shrink-0 rounded border border-zinc-300 bg-white px-0.5 py-1 text-[11px] disabled:opacity-50">
                <option value="global">国际站</option>
                <option value="china">中国站</option>
                <option value="fallback">备用站</option>
              </select>
              {busy ? (
                <span className="shrink-0 text-[10px] text-amber-700">运行中</span>
              ) : (
                <button type="button" onClick={() => setVisible((prev) => ({ ...prev, [i]: !prev[i] }))}
                  className="shrink-0 text-[11px] text-zinc-500 hover:text-indigo-600">{visible[i] ? '隐藏' : '显示'}</button>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-zinc-500">如果其他Key返回401，请核对它们的注册站点；503/队列已满是供应商容量问题，切站点不能保证成功。切换仅影响后续新任务。</p>
    </div>
  );
}
