import type { TaskState } from '../lib/types';
import { cn } from '../utils/cn';

interface Props {
  keyCount: number;
  apiKeys: string[];
  tasksByKey: Record<number, TaskState>;
  onGenerate: (keyIndex: number) => void;
  onStop: (keyIndex: number) => void;
  onGenerateAll: () => void;
}

const BUSY_STATUSES = new Set(['creating', 'queued', 'in_progress']);

export default function GenerateBar({ keyCount, apiKeys, tasksByKey, onGenerate, onStop, onGenerateAll }: Props) {
  const hasRunnableKey = Array.from({ length: keyCount }).some((_, i) => {
    const busy = BUSY_STATUSES.has(tasksByKey[i]?.status ?? 'idle');
    return !busy && !!apiKeys[i]?.trim();
  });

  return (
    <div className="flex flex-wrap items-center gap-2">
      {Array.from({ length: keyCount }).map((_, i) => {
        const state = tasksByKey[i];
        const busy = BUSY_STATUSES.has(state?.status ?? 'idle');
        const hasKey = !!apiKeys[i]?.trim();
        return (
          <button
            key={i}
            type="button"
            disabled={!hasKey && !busy}
            onClick={() => (busy ? onStop(i) : onGenerate(i))}
            title={busy ? '仅停止状态轮询，不取消服务端已创建的生成任务' : !hasKey ? `请先填写 Key ${i + 1}` : undefined}
            className={cn(
              'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-40',
              busy
                ? 'bg-rose-600 text-white hover:bg-rose-700'
                : 'bg-indigo-600 text-white hover:bg-indigo-700',
            )}
          >
            {busy ? (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="m5 3 14 9-14 9V3z" />
              </svg>
            )}
            <span>
              {busy ? '停止跟踪' : '生成视频'}
              {keyCount > 1 ? ` · Key${i + 1}` : ''}
            </span>
          </button>
        );
      })}
      {keyCount > 1 ? (
        <button
          type="button"
          onClick={onGenerateAll}
          disabled={!hasRunnableKey}
          className="flex items-center gap-2 rounded-lg border-2 border-indigo-600 bg-white px-4 py-2.5 text-sm font-semibold text-indigo-600 shadow-sm transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
          </svg>
          一键生成全部可用 Key
        </button>
      ) : null}
    </div>
  );
}
