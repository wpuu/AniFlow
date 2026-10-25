import type { TaskState } from '../lib/types';
import { selectGeneratableKeys } from '../lib/eligibleKeys';
import { cn } from '../utils/cn';

interface Props {
  keyCount: number;
  apiKeys: string[];
  tasksByKey: Record<number, TaskState>;
  onGenerate: (keyIndex: number) => void;
  onGenerateAll: () => void;
}

export default function GenerateBar({ keyCount, apiKeys, tasksByKey, onGenerate, onGenerateAll }: Props) {
  const ready = new Set(selectGeneratableKeys(apiKeys, keyCount, tasksByKey));
  return (
    <div className="flex flex-nowrap items-center gap-1.5 overflow-x-auto pb-1" aria-label="生成任务操作">
      {Array.from({ length: keyCount }).map((_, i) => {
        const status = tasksByKey[i]?.status ?? 'idle';
        const available = ready.has(i);
        const active = ['creating', 'queued', 'in_progress'].includes(status);
        const label = `key${i + 1}`;
        return (
          <button
            key={i}
            type="button"
            data-testid={`generate-key-${i + 1}`}
            disabled={!available}
            onClick={() => onGenerate(i)}
            aria-label={label}
            title={active
              ? `${label} 正在生成或等待中，不中断现有任务`
              : !apiKeys[i]?.trim()
                ? `${label} 未填写 API Key`
                : !available ? '当前 Key 与其他槽位重复或已有相同密钥在运行' : `${label} 创建一个视频`}
            className={cn(
              'shrink-0 rounded-md px-2.5 py-1.5 text-xs font-semibold transition',
              available
                ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                : active ? 'cursor-not-allowed bg-amber-100 text-amber-700'
                  : 'cursor-not-allowed bg-zinc-100 text-zinc-400',
            )}
          >{label}</button>
        );
      })}
      <button
        type="button"
        data-testid="generate-ready-all"
        onClick={onGenerateAll}
        disabled={ready.size === 0}
        title="只提交当前可用且不重复的 Key；不会停止或重启正在生成的任务"
        className="shrink-0 rounded-md border border-indigo-600 bg-white px-2.5 py-1.5 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40"
      >一键生成</button>
    </div>
  );
}
