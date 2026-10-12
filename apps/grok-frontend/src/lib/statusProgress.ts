import type { HistoryItem, TaskState, TaskStatus } from './types';

export function percentValue(raw: unknown, status?: TaskStatus, hasVideo = false): number {
  if (status === 'completed' && hasVideo) return 100;
  const value = typeof raw === 'number' && Number.isFinite(raw) ? raw : 0;
  return Math.round(Math.min(100, Math.max(0, value)));
}

export interface KeyProgressSummary {
  status: TaskStatus;
  progress: number;
}

/** Expose actual provider progress; never fabricate progress before Agnes supplies it. */
export function keyProgressSummary(
  keyIndex: number,
  tasks: Record<number, TaskState>,
  history: HistoryItem[],
): KeyProgressSummary {
  const live = tasks[keyIndex];
  const recent = history
    .filter((item) => item.keyIndex === keyIndex)
    .sort((a, b) => b.createdAt - a.createdAt)[0];
  const useLive = live && live.status !== 'idle'
    && (!recent || recent.status === 'creating' || recent.status === live.status
      || (live.videoId && live.videoId === recent.videoId));
  const status = (useLive ? live.status : recent?.status) || 'idle';
  const progress = percentValue(
    useLive ? live.progress : recent?.progress,
    status,
    Boolean((useLive ? live.videoUrl : recent?.videoUrl)),
  );
  return { status, progress };
}
