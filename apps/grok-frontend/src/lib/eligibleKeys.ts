import type { TaskState } from './types';

const ACTIVE_STATUSES = new Set(['creating', 'queued', 'in_progress']);

/** The compact buttons and batch submission use exactly the same eligibility. */
export function selectGeneratableKeys(
  keys: readonly string[],
  count: number,
  tasks: Readonly<Record<number, TaskState>>,
  submitting: ReadonlySet<number> = new Set<number>(),
): number[] {
  const cap = Math.min(9, Math.max(0, count));
  const used = new Set<string>();
  for (let i = 0; i < cap; i += 1) {
    const key = keys[i]?.trim();
    if (key && (submitting.has(i) || ACTIVE_STATUSES.has(tasks[i]?.status ?? 'idle'))) used.add(key);
  }
  const eligible: number[] = [];
  for (let i = 0; i < cap; i += 1) {
    const key = keys[i]?.trim();
    if (!key || submitting.has(i) || ACTIVE_STATUSES.has(tasks[i]?.status ?? 'idle') || used.has(key)) continue;
    eligible.push(i);
    used.add(key);
  }
  return eligible;
}
