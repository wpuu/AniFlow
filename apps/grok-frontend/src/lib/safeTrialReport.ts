import type { HistoryItem, TaskStatus, VideoModelKey } from './types';

const ALLOWED_STATUSES: ReadonlySet<string> = new Set([
  'idle', 'creating', 'queued', 'in_progress', 'completed',
  'failed', 'stopped', 'submission_unknown',
]);

function safeStatus(value: unknown): TaskStatus | 'unknown' {
  return typeof value === 'string' && ALLOWED_STATUSES.has(value)
    ? (value as TaskStatus) : 'unknown';
}

function errorClass(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'none';
  if (typeof value !== 'string') return 'other';
  if (/queue[_ -]?full|video_queue_full|排队|队列/.test(value.toLowerCase())) return 'queue_full';
  if (/401|403|invalid.?key|unauthoriz|forbidden/.test(value.toLowerCase())) return 'auth';
  if (/timed? ?out|网络|network|断开|cors/.test(value.toLowerCase())) return 'network';
  return 'other';
}

function elapsedSeconds(begin: unknown, finish: unknown): number | null {
  if (typeof begin !== 'number' || typeof finish !== 'number'
    || !Number.isFinite(begin) || !Number.isFinite(finish) || finish < begin) return null;
  return Math.floor((finish - begin) / 1000);
}

function safeModel(model: unknown): string {
  return model === 'flash25' ? 'Agnes Video 2.5 Flash'
    : model === 'v2' ? 'Agnes Video V2.0' : 'unknown';
}

export interface SafeTrialItem {
  key_slot: number;
  has_configured_key: boolean;
  has_unresolved_submission: boolean;
  model: string;
  status: string;
  has_video_id: boolean;
  has_download_url: boolean;
  error_category: string;
  elapsed_to_final_seconds: number | null;
  elapsed_since_submission_seconds: number | null;
}

/** Only short aggregate evidence leaves the browser. Never emit Key, prompt, ID, URL, or errors. */
export function buildSafeTrialReport(
  configuredKeys: boolean[],
  history: HistoryItem[],
  guardIndexes: number[],
  nowMs: number,
): string {
  const keys = configuredKeys.slice(0, 9).map((configured, index): SafeTrialItem => {
    const recent = history
      .filter((entry) => entry.keyIndex === index)
      .sort((a, b) => b.createdAt - a.createdAt)[0];
    const status = safeStatus(recent?.status);
    return {
      key_slot: index + 1,
      has_configured_key: Boolean(configured),
      has_unresolved_submission: guardIndexes.includes(index),
      model: safeModel(recent?.modelKey as VideoModelKey | undefined),
      status: recent ? status : 'none',
      has_video_id: Boolean(recent?.videoId),
      has_download_url: Boolean(
        typeof recent?.videoUrl === 'string' && /^https?:\/\//i.test(recent.videoUrl),
      ),
      error_category: errorClass(recent?.error),
      elapsed_to_final_seconds: elapsedSeconds(recent?.createdAt, recent?.finishedAt),
      elapsed_since_submission_seconds: recent
        ? elapsedSeconds(recent.createdAt, nowMs) : null,
    };
  });

  const report = {
    report: 'AniFlow 9-Key Agnes video trial (sanitized)',
    exported_at_utc: new Date(nowMs).toISOString(),
    source: 'browser-local-history',
    task_scope: 'most recent task per key slot',
    no_new_generation_requests: true,
    contains_api_keys: false,
    contains_video_urls: false,
    contains_video_ids: false,
    contains_raw_errors: false,
    configured_count: keys.filter((k) => k.has_configured_key).length,
    blocked_pending_count: keys.filter((k) => k.has_unresolved_submission).length,
    keys,
    caveat: 'A browser snapshot is not vendor billing, provider capacity, or human MP4 quality proof.',
  };
  return JSON.stringify(report, null, 2);
}
