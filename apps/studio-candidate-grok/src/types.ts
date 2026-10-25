export type TaskStatus = "queued" | "running" | "done" | "failed";
export type AspectRatio = "16:9" | "9:16" | "1:1" | "4:3" | "21:9";
export type BackendId = "minimax" | "agnes" | "huggingface";
export type ModelStatus = "ready" | "busy" | "degraded" | "offline";

export interface Model {
  id: string;
  name: string;
  shortName: string;
  backend: BackendId;
  backendLabel: string;
  status: ModelStatus;
  latencyMs: number;
  costPerSecond: number;
  maxDuration: number;
  description: string;
  queue: number;
  tags: string[];
}

export interface Task {
  id: string;
  prompt: string;
  negativePrompt: string;
  modelId: string;
  aspectRatio: AspectRatio;
  duration: number;
  fps: number;
  seed: number;
  cfg: number;
  motion: number;
  status: TaskStatus;
  progress: number;
  etaSeconds: number;
  cost: number;
  createdAt: number;
  startedAt?: number;
  finishedAt?: number;
  firstFrame?: string;
  videoUrl?: string;
  thumbnailUrl?: string;
  error?: string;
}

export interface CreatePayload {
  prompt: string;
  negativePrompt: string;
  modelId: string;
  aspectRatio: AspectRatio;
  duration: number;
  fps: number;
  seed: number;
  cfg: number;
  motion: number;
  firstFrame?: string;
}

export type StatusFilter = "all" | TaskStatus;
