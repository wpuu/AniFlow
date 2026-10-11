import type { VideoModelKey } from './types';

export interface SubmissionGuard {
  attemptId: string;
  keyIndex: number;
  modelKey: VideoModelKey;
  createdAt: number;
  videoId: string | null;
}

export type SubmissionGuards = Record<string, SubmissionGuard>;

/** Treat malformed persisted guards as unsafe instead of silently allowing a new POST. */
export function isValidSubmissionGuards(value: unknown): value is SubmissionGuards {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.entries(value).every(([index, guard]) => {
    if (!guard || typeof guard !== 'object' || Array.isArray(guard)) return false;
    const item = guard as Partial<SubmissionGuard>;
    return typeof item.keyIndex === 'number'
      && Number.isInteger(item.keyIndex)
      && item.keyIndex >= 0
      && item.keyIndex <= 8
      && index === String(item.keyIndex)
      && typeof item.attemptId === 'string'
      && item.attemptId.length > 0
      && (item.modelKey === 'flash25' || item.modelKey === 'v2')
      && typeof item.createdAt === 'number'
      && Number.isFinite(item.createdAt)
      && (item.videoId === null || (typeof item.videoId === 'string' && item.videoId.length > 0));
  });
}

/** Avoid releasing the once-only request lock for a completed task with no video. */
export function shouldReleaseVideoGuard(status: string, videoUrl: string | null | undefined): boolean {
  if (status === 'failed') return true;
  if (status !== 'completed' || !videoUrl) return false;
  try {
    const url = new URL(videoUrl);
    return url.protocol === 'https:' || url.protocol === 'http:';
  } catch {
    return false;
  }
}

export function reserveAttempt(
  guards: SubmissionGuards,
  attempt: SubmissionGuard,
): SubmissionGuards | null {
  const index = String(attempt.keyIndex);
  if (guards[index]) return null;
  return { ...guards, [index]: attempt };
}

export function attachVideoId(
  guards: SubmissionGuards,
  keyIndex: number,
  attemptId: string,
  videoId: string,
): SubmissionGuards {
  const index = String(keyIndex);
  const existing = guards[index];
  if (!existing || existing.attemptId !== attemptId || !videoId.trim()) return guards;
  return { ...guards, [index]: { ...existing, videoId } };
}

export function releaseAttempt(
  guards: SubmissionGuards,
  keyIndex: number,
  attemptId: string,
): SubmissionGuards {
  const index = String(keyIndex);
  if (guards[index]?.attemptId !== attemptId) return guards;
  const next = { ...guards };
  delete next[index];
  return next;
}
