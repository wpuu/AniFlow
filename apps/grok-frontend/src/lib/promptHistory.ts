import type { VideoModelKey } from './types';

export interface SavedPrompt {
  id: string;
  prompt: string;
  modelKey: VideoModelKey;
  savedAt: number;
}

export function rememberPrompt(
  existing: readonly SavedPrompt[],
  value: string,
  modelKey: VideoModelKey,
  now: number,
): SavedPrompt[] {
  const prompt = value.trim();
  if (!prompt) return [...existing];
  const remainder = existing.filter((item) => item.prompt !== prompt);
  return [
    { id: `prompt-${now}-${remainder.length}`, prompt, modelKey, savedAt: now },
    ...remainder,
  ].slice(0, 40);
}

export function safePromptHeight(raw: unknown): number {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return 180;
  return Math.min(900, Math.max(120, Math.round(raw)));
}
