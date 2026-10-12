/**
 * Only READ-only status GETs are retried. Never retry video creation here.
 * The time window is an AniFlow client policy, not an Agnes SLA.
 */
export const STATUS_POLL_WINDOW_MS = 20 * 60 * 1000;
export const STATUS_POLL_SUCCESS_INTERVAL_MS = 6_000;

export function isWithinStatusWindow(startedAt: number, now: number): boolean {
  return Number.isFinite(startedAt)
    && Number.isFinite(now)
    && now >= startedAt
    && now - startedAt < STATUS_POLL_WINDOW_MS;
}

export function retryableStatusDelayMs(reason: string): number | null {
  const httpCode = /^HTTP\s+(\d{3})\b/i.exec(reason)?.[1];
  if (httpCode === '404') return 12_000;  // accepted video_id may not yet be visible
  if (httpCode === '408') return 15_000;
  if (httpCode === '429') return 30_000;
  if (httpCode && ['500', '502', '503', '504', '520'].includes(httpCode)) return 25_000;
  if (httpCode) return null; // 400, 401, 403, 422 are not transient
  if (/failed to fetch|network|networkerror|timeout|timed out|连接失败|网络异常|temporarily unavailable/i.test(reason)) {
    return 15_000;
  }
  return null;
}
