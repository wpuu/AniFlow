import { useMemo } from 'react';
import type { HistoryItem, TaskState } from '../lib/types';
import { STATUS_COLORS, STATUS_LABELS, VIDEO_MODELS } from '../lib/constants';
import { formatTime, modeLabel } from '../lib/format';
import { keyProgressSummary, percentValue } from '../lib/statusProgress';
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
  const currentTask = tasksByKey[selectedKeyTab];
  const snapshot = keyProgressSummary(selectedKeyTab, tasksByKey, history);
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
        modelKey: activeItem.modelKey ?? 'v2',
      }
    : currentTask && currentTask.status !== 'idle'
      ? {
          ...currentTask,
          promptPreview: '',
          mode: 'unknown',
          ratio: 'unknown',
          resolution: 'unknown',
          createdAt: Date.now(),
          modelKey: currentTask.modelKey ?? 'flash25',
        }
      : null;
  const selectedProgress = display
    ? percentValue(display.progress, display.status, Boolean(display.videoUrl))
    : snapshot.progress;

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="rounded-xl border border-zinc-200 bg-white p-2">
        <p className="mb-2 text-[11px] text-zinc-500">点击数字查看对应 Key 的状态和真实进度</p>
        <div className="grid grid-cols-9 gap-1" role="tablist" aria-label="9个视频 Key 的任务状态">
          {Array.from({ length: keyCount }).map((_, i) => {
            const state = keyProgressSummary(i, tasksByKey, history);
            const active = selectedKeyTab === i;
            const textColor = state.status === 'completed' ? 'text-emerald-700'
              : state.status === 'failed' ? 'text-rose-600'
                : state.status === 'submission_unknown' ? 'text-amber-700'
                  : state.status === 'in_progress' ? 'text-sky-700' : 'text-zinc-500';
            return (
              <button
                key={i}
                type="button"
                role="tab"
                aria-selected={active}
                aria-controls="aniflow-key-details"
                aria-label={`第${i + 1}个Key：${STATUS_LABELS[state.status]}，${state.progress}%`}
                data-testid={`key-tab-${i + 1}`}
                onClick={() => onSelectKeyTab(i)}
                title={`Key ${i + 1}：${STATUS_LABELS[state.status]} ${state.progress}%`}
                className={cn(
                  'min-w-0 rounded-md border px-0.5 py-2 text-center transition',
                  active ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
                    : 'border-zinc-200 bg-zinc-50 hover:bg-zinc-100',
                )}
              >
                <span className="block text-sm font-bold leading-none">{i + 1}</span>
                <span className={cn('mt-1 block text-[10px] font-medium tabular-nums', textColor)}
                  data-testid={`key-progress-${i + 1}`}>{state.progress}%</span>
              </button>
            );
          })}
        </div>
      </div>

      <div id="aniflow-key-details" role="tabpanel" className="rounded-xl border border-zinc-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div>
            <span className="text-sm font-semibold text-zinc-800">第 {selectedKeyTab + 1} 个 Key · 视频预览</span>
            {display ? (
              <p className="mt-0.5 text-[10px] text-zinc-400">{VIDEO_MODELS[display.modelKey]?.label ?? '历史模型'}</p>
            ) : null}
          </div>
          <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', STATUS_COLORS[display?.status || snapshot.status])}>
            {STATUS_LABELS[display?.status || snapshot.status] ?? snapshot.status}
          </span>
        </div>
        <div className="mb-3">
          <div className="mb-1 flex justify-between text-xs text-zinc-500">
            <span>生成进度</span><span className="font-semibold tabular-nums text-zinc-800" data-testid="selected-progress">{selectedProgress}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100" role="progressbar"
            aria-label={`Key ${selectedKeyTab + 1} 的进度`}
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={selectedProgress}>
            <div className={cn('h-full rounded-full transition-all', display?.status === 'failed' ? 'bg-rose-500' : 'bg-indigo-500')}
              style={{ width: `${selectedProgress}%` }} />
          </div>
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
                {display && ['creating', 'queued', 'in_progress'].includes(display.status)
                  ? '视频生成或排队中，等待服务端反馈进度…'
                  : '暂无可播放视频'}
              </p>
            </div>
          )}
        </div>
        {display?.error ? (
          <p className="mt-2 rounded-md bg-rose-50 px-2 py-1.5 text-xs text-rose-600">错误：{display.error}</p>
        ) : null}
        {display?.videoUrl ? (
          <div className="mt-3 space-y-1.5">
            <p className="text-xs font-medium text-zinc-500">生成地址（可能过期，请保存）</p>
            <a href={display.videoUrl} target="_blank" rel="noopener noreferrer"
              className="block truncate rounded-md bg-indigo-50 px-2.5 py-1.5 text-xs text-indigo-600 underline decoration-dotted hover:bg-indigo-100">
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
          <span className="text-sm font-semibold text-zinc-800">历史记录（{selectedKeyTab + 1}）</span>
          <span className="text-[11px] text-zinc-400">{keyHistory.length} 条</span>
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto pr-0.5">
          {keyHistory.length === 0 ? (
            <p className="py-6 text-center text-xs text-zinc-400">该 Key 暂无历史生成记录</p>
          ) : keyHistory.map((item) => (
            <div key={item.id} role="button" tabIndex={0}
              onClick={() => onSelectHistory(selectedKeyTab, item.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSelectHistory(selectedKeyTab, item.id); }}
              className={cn('w-full cursor-pointer rounded-lg border px-3 py-2 text-left transition',
                item.id === selectedId ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500'
                  : 'border-zinc-200 hover:border-zinc-300')}>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-zinc-400">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-medium text-zinc-500">{modeLabel(item.mode)}</span>
                  <span className="truncate">{VIDEO_MODELS[item.modelKey ?? 'v2']?.label ?? '历史模型'}</span>
                  <span>{item.ratio}</span>
                </span>
                <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium',
                  STATUS_COLORS[item.status])}>
                  {STATUS_LABELS[item.status] ?? item.status}
                </span>
              </div>
              <p className="line-clamp-2 text-xs text-zinc-700">{item.promptPreview || '（未填写提示词）'}</p>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10px] text-zinc-400">{formatTime(item.createdAt)}</span>
                {(item.status === 'queued' || item.status === 'in_progress'
                  || item.status === 'creating' || item.status === 'stopped'
                  || item.status === 'submission_unknown') && !!item.videoId ? (
                  <button type="button" onClick={(e) => { e.stopPropagation(); onRefreshHistory(item); }}
                    className="text-[10px] text-indigo-500 hover:underline">刷新状态</button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
