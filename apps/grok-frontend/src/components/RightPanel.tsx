import { useEffect, useMemo, useRef, useState } from 'react';
import type { HistoryItem, TaskState } from '../lib/types';
import { STATUS_COLORS, STATUS_LABELS } from '../lib/constants';
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
  onStopTracking: (keyIndex: number) => void;
}

export default function RightPanel({
  keyCount, selectedKeyTab, onSelectKeyTab,
  tasksByKey, history, selectedHistoryIdByKey,
  onSelectHistory, onRefreshHistory, onStopTracking,
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
    ? activeItem
    : currentTask && currentTask.status !== 'idle'
      ? {
          ...currentTask,
          id: '', keyIndex: selectedKeyTab, createdAt: Date.now(),
          promptPreview: '', mode: 'unknown' as const,
          ratio: 'unknown' as const, resolution: 'unknown' as const,
        }
      : null;
  const selectedProgress = display
    ? percentValue(display.progress, display.status, Boolean(display.videoUrl))
    : snapshot.progress;
  const isCurrentBusy = ['creating', 'queued', 'in_progress'].includes(currentTask?.status ?? '');
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    video.current?.pause();
    setPlaying(false);
  }, [selectedKeyTab, selectedId, display?.videoUrl]);

  function togglePlayback() {
    const element = video.current;
    if (!element) return;
    if (element.paused) {
      void element.play().catch(() => setPlaying(false));
    } else {
      element.pause();
    }
  }

  return (
    <section className="space-y-3" aria-label="视频控制与历史">
      <div className="rounded-xl border border-zinc-200 bg-white p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-zinc-800">视频控制 / 历史</h2>
          <span className="text-[11px] text-zinc-500">选择 Key 查看视频及结果</span>
        </div>
        <div className="grid grid-cols-9 gap-1" role="tablist" aria-label="9个视频 Key 的任务状态">
          {Array.from({ length: keyCount }).map((_, i) => {
            const state = keyProgressSummary(i, tasksByKey, history);
            const active = selectedKeyTab === i;
            const textColor = state.status === 'completed' ? 'text-emerald-700'
              : state.status === 'failed' ? 'text-rose-600'
                : state.status === 'submission_unknown' ? 'text-amber-700'
                  : state.status === 'in_progress' ? 'text-sky-700' : 'text-zinc-500';
            return (
              <button key={i} type="button" role="tab" aria-selected={active}
                aria-controls="aniflow-key-details"
                aria-label={`第${i + 1}个Key：${STATUS_LABELS[state.status]}，${state.progress}%`}
                data-testid={`key-tab-${i + 1}`}
                onClick={() => onSelectKeyTab(i)}
                title={`Key ${i + 1}：${STATUS_LABELS[state.status]} ${state.progress}%`}
                className={cn(
                  'min-w-0 rounded-md border px-0.5 py-1.5 text-center transition',
                  active ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
                    : 'border-zinc-200 bg-zinc-50 hover:bg-zinc-100',
                )}>
                <span className="block text-xs font-bold leading-none">{i + 1}</span>
                <span className={cn('mt-1 block text-[10px] font-medium tabular-nums', textColor)}
                  data-testid={`key-progress-${i + 1}`}>{state.progress}%</span>
              </button>
            );
          })}
        </div>
      </div>

      <div id="aniflow-key-details" role="tabpanel" className="rounded-xl border border-zinc-200 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-sm font-semibold text-zinc-800">key{selectedKeyTab + 1}</span>
            <span className={cn(
              'rounded-full px-2 py-0.5 text-[11px] font-medium',
              STATUS_COLORS[display?.status || snapshot.status],
            )}>{STATUS_LABELS[display?.status || snapshot.status] ?? snapshot.status}</span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5" aria-label="视频快捷操作">
            <button type="button" onClick={togglePlayback} disabled={!display?.videoUrl}
              className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 disabled:opacity-40"
              data-testid="quick-play-video">{playing ? '暂停' : '播放'}</button>
            {display?.videoUrl ? (
              <a href={display.videoUrl} target="_blank" rel="noopener noreferrer"
                className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700">打开视频</a>
            ) : null}
            {isCurrentBusy ? (
              <button type="button" onClick={() => onStopTracking(selectedKeyTab)}
                title="只停止本机查询，服务器上已创建的任务仍可能继续"
                className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-600">
                停止跟踪
              </button>
            ) : null}
          </div>
        </div>

        <div className="mt-2 mb-3">
          <div className="mb-1 flex justify-between text-[11px] text-zinc-500">
            <span>生成进度</span>
            <span className="font-semibold tabular-nums" data-testid="selected-progress">{selectedProgress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100" role="progressbar"
            aria-label={`Key ${selectedKeyTab + 1} 的进度`}
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={selectedProgress}>
            <div className={cn('h-full rounded-full transition-all', display?.status === 'failed'
              ? 'bg-rose-500' : 'bg-indigo-500')} style={{ width: `${selectedProgress}%` }} />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(185px,0.9fr)]">
          <div className="order-2 min-w-0 sm:order-1">
            <div className="flex h-[300px] max-h-[40vh] min-h-[220px] w-full items-center justify-center overflow-hidden rounded-lg bg-zinc-900">
              {display?.videoUrl ? (
                <video ref={video} key={display.videoUrl} src={display.videoUrl}
                  controls playsInline preload="metadata"
                  onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
                  onEnded={() => setPlaying(false)}
                  className="h-full w-full object-contain"
                  data-testid="aniflow-video-preview" />
              ) : (
                <p className="px-4 text-center text-xs leading-relaxed text-zinc-400">
                  {display && ['creating', 'queued', 'in_progress'].includes(display.status)
                    ? '正在提交、排队或生成，等待上游进度。'
                    : '暂无可播放视频'}
                </p>
              )}
            </div>
            {display?.error ? (
              <p className={cn(
                'mt-2 break-words rounded-md px-2 py-1.5 text-xs',
                ['queued', 'in_progress'].includes(display.status)
                  ? 'bg-amber-50 text-amber-800' : 'bg-rose-50 text-rose-700',
              )} data-testid="selected-task-error">
                {['queued', 'in_progress'].includes(display.status) ? '查询提示：' : '错误：'}
                {display.error}
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500">
              {display?.size ? <span>画幅：{display.size}</span> : null}
              {display?.seconds ? <span>时长：{display.seconds}秒</span> : null}
              {display?.mode && display.mode !== 'unknown'
                ? <span>模式：{modeLabel(display.mode)}</span> : null}
            </div>
          </div>

          <aside className="order-1 flex min-h-0 min-w-0 flex-col sm:order-2">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <strong className="text-xs text-zinc-700">历史记录</strong>
              <span className="text-[11px] text-zinc-500">{keyHistory.length}条</span>
            </div>
            <div className="max-h-[310px] min-h-[100px] space-y-1.5 overflow-y-auto rounded-md border border-zinc-200 p-1"
              aria-label={`历史记录（${selectedKeyTab + 1}）`}>
              {keyHistory.length === 0 ? (
                <p className="px-2 py-4 text-center text-xs text-zinc-400">暂无历史</p>
              ) : keyHistory.map((item) => (
                <div key={item.id} className={cn(
                  'rounded-md border px-2 py-1.5',
                  item.id === selectedId ? 'border-indigo-500 bg-indigo-50/60'
                    : 'border-zinc-200 bg-white',
                )}>
                  <button type="button" onClick={() => onSelectHistory(selectedKeyTab, item.id)}
                    aria-label={`切换历史：${formatTime(item.createdAt)}，${STATUS_LABELS[item.status]}`}
                    className="block w-full text-left">
                    <span className="flex flex-wrap items-center justify-between gap-1">
                      <span className="text-[10px] text-zinc-500">{formatTime(item.createdAt)}</span>
                      <span className="text-[10px] font-semibold text-zinc-600">{STATUS_LABELS[item.status]}</span>
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-zinc-700">
                      {item.promptPreview || '（无提示词摘要）'}
                    </span>
                  </button>
                  {item.videoId && ['queued', 'in_progress', 'creating', 'stopped', 'submission_unknown'].includes(item.status) ? (
                    <button type="button" onClick={() => onRefreshHistory(item)}
                      className="mt-1 text-[11px] text-indigo-600 hover:underline">刷新状态</button>
                  ) : null}
                </div>
              ))}
            </div>
          </aside>
        </div>
        <p className="mt-2 text-[10px] text-zinc-400">
          播放控制在上方；刷新历史只查询已知视频编号，不会重新生成。
        </p>
      </div>
    </section>
  );
}
