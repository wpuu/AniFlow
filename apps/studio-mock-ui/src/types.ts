export type TaskStatus = "queued" | "running" | "submission_unknown" | "downloading" | "done" | "failed";
export type StudioMode = "mock" | "real";
export type RealProvider = "minimax-h3" | "wan2.2-i2v-a14b";
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
  progress: number | null;
  etaSeconds: number | null;
  cost: number | null;
  createdAt: number;
  startedAt?: number;
  finishedAt?: number;
  firstFrame?: string;
  videoUrl?: string;
  thumbnailUrl?: string;
  error?: string;
  promptId?: string;
  localPath?: string;
  sha256?: string;
  outputBytes?: number;
  verified?: boolean;
  elapsedSeconds?: number | null;
  peakVramMb?: number | null;
  videoMetadata?: { duration_seconds: number; width: number; height: number; fps: number;
    frame_count?: number; sample_aspect_ratio?: string };
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
