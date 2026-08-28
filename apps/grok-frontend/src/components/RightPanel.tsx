import { useMemo } from 'react';
import type { HistoryItem, TaskState } from '../lib/types';
import { STATUS_COLORS, STATUS_LABELS } from '../lib/constants';
import { formatTime, modeLabel } from '../lib/format';
import { cn } from '../utils/cn';

interface Props {
  keyCount: number;
  selectedKeyTab: number;
  onSelectKeyTab: (i: number) => void;
  tasksByKey: Record<number, TaskState>;
  history: HistoryItem[];
  selectedHistoryIdByKey: Record<number, string | undefined>;
  onSelectHistory: (keyIndex: number, id: string) => void;
  onRefreshHistory: (item: HistoryItem) => void;
}

export default function RightPanel({
  keyCount,
  selectedKeyTab,
  onSelectKeyTab,
  tasksByKey,
  history,
  selectedHistoryIdByKey,
  onSelectHistory,
  onRefreshHistory,
}: Props) {
  const keyHistory = useMemo(
    () => history.filter((h) => h.keyIndex === selectedKeyTab).sort((a, b) => b.createdAt - a.createdAt),
    [history, selectedKeyTab],
  );

  const selectedId = selectedHistoryIdByKey[selectedKeyTab] ?? keyHistory[0]?.id;
  const activeItem = keyHistory.find((h) => h.id === selectedId) ?? keyHistory[0];
  const liveTask = tasksByKey[selectedKeyTab];

  // 优先展示与当前选中历史一致的实时任务信息（正在进行中的任务）
  const display = activeItem
    ? {
        status: activeItem.status,
        progress: activeItem.progress,
        videoUrl: activeItem.videoUrl,
        error: activeItem.error,
        size: activeItem.size,
        seconds: activeItem.seconds,
        promptPreview: activeItem.promptPreview,
        mode: activeItem.mode,
        ratio: activeItem.ratio,
        resolution: activeItem.resolution,
        createdAt: activeItem.createdAt,
      }
    : null;

  return (
    <div className="flex h-full flex-col gap-4">
      {keyCount > 1 ? (
        <div className="flex flex-wrap gap-1.5 rounded-lg bg-zinc-100 p-1">
          {Array.from({ length: keyCount }).map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onSelectKeyTab(i)}
              className={cn(
                'flex-1 rounded-md px-2 py-1.5 text-xs font-semibold transition',
                selectedKeyTab === i ? 'bg-white text-indigo-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700',
              )}
            >
              Key {i + 1}
            </button>
          ))}
        </div>
      ) : null}

      <div className="rounded-xl border border-zinc-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold text-zinc-800">视频预览</span>
          {display ? (
            <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', STATUS_COLORS[display.status])}>
              {STATUS_LABELS[display.status] ?? display.status}
            </span>
          ) : null}
        </div>

        <div className="flex aspect-[9/16] w-full max-h-[480px] items-center justify-center overflow-hidden rounded-lg bg-zinc-900">
          {display?.videoUrl ? (
            <video src={display.videoUrl} controls className="h-full w-full object-contain" />
          ) : (
            <div className="flex flex-col items-center gap-2 px-6 text-center text-zinc-400">
              <svg className="h-10 w-10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="m10 9 5 3-5 3V9z" />
              </svg>
              <p className="text-xs leading-relaxed">
                {display
                  ? liveTask?.status && liveTask.status !== 'idle'
                    ? '视频生成中，请稍候…'
                    : '暂无可播放视频'
                  : '尚无生成记录，设置参数后点击上方“生成视频”开始'}
              </p>
            </div>
          )}
        </div>

        {display && display.status !== 'completed' && display.status !== 'idle' ? (
          <div className="mt-3 space-y-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  display.status === 'failed' ? 'bg-rose-500' : 'bg-indigo-500',
                )}
                style={{ width: `${Math.min(100, Math.max(4, display.progress))}%` }}
              />
            </div>
            <p className="text-right text-[11px] text-zinc-400">{display.progress}%</p>
          </div>
        ) : null}

        {display?.error ? (
          <p className="mt-2 rounded-md bg-rose-50 px-2 py-1.5 text-xs text-rose-600">错误：{display.error}</p>
        ) : null}

        {display?.videoUrl ? (
          <div className="mt-3 space-y-1.5">
            <p className="text-xs font-medium text-zinc-500">生成地址</p>
            <a
              href={display.videoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="block truncate rounded-md bg-indigo-50 px-2.5 py-1.5 text-xs text-indigo-600 underline decoration-dotted hover:bg-indigo-100"
            >
              {display.videoUrl}
            </a>
            <div className="flex gap-3 text-[11px] text-zinc-400">
              {display.size ? <span>分辨率：{display.size}</span> : null}
              {display.seconds ? <span>时长：{display.seconds}s</span> : null}
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-zinc-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold text-zinc-800">历史记录（Key {selectedKeyTab + 1}）</span>
          <span className="text-[11px] text-zinc-400">{keyHistory.length} 条</span>
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto pr-0.5">
          {keyHistory.length === 0 ? (
            <p className="py-6 text-center text-xs text-zinc-400">该 Key 暂无历史生成记录</p>
          ) : (
            keyHistory.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectHistory(selectedKeyTab, item.id)}
                className={cn(
                  'block w-full rounded-lg border px-3 py-2 text-left transition',
                  item.id === selectedId
                    ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500'
                    : 'border-zinc-200 hover:border-zinc-300',
                )}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                    <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-medium text-zinc-500">
                      {modeLabel(item.mode)}
                    </span>
                    <span>{item.ratio}</span>
                    <span>{item.resolution}</span>
                  </span>
                  <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium', STATUS_COLORS[item.status])}>
                    {STATUS_LABELS[item.status] ?? item.status}
                  </span>
                </div>
                <p className="line-clamp-2 text-xs text-zinc-700">{item.promptPreview || '（未填写提示词）'}</p>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-[10px] text-zinc-400">{formatTime(item.createdAt)}</span>
                  {item.status === 'queued' || item.status === 'in_progress' || item.status === 'creating' ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRefreshHistory(item);
                      }}
                      className="text-[10px] text-indigo-500 hover:underline"
                    >
                      刷新状态
                    </button>
                  ) : null}
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
