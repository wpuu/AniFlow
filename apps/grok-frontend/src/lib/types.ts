export type Ratio = '16:9' | '9:16' | '1:1' | '4:3' | '3:4';
export type ResolutionTier = '480p' | '720p' | '1080p';
export type VideoModelKey = 'v2' | 'flash25';
export type GenMode = 't2v' | 'i2v' | 'keyframes';
export type DurationPresetKey = '3' | '5' | '10' | '18' | 'custom';

export type TaskStatus =
  | 'idle'
  | 'creating'
  | 'queued'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'stopped';

export interface KeyframeScene {
  id: string;
  imageUrl: string;
  fileName?: string;
}

export interface GenerationParams {
  mode: GenMode;
  prompt: string;
  negativePrompt: string;
  ratio: Ratio;
  resolution: ResolutionTier;
  width: number;
  height: number;
  durationPreset: DurationPresetKey;
  numFrames: number;
  frameRate: number;
  seconds: number;
  numInferenceSteps: number | '';
  seed: number | '';
  singleImage: string;
  singleImageFileName?: string;
  keyframeScenes: KeyframeScene[];
}

export interface TaskState {
  status: TaskStatus;
  progress: number;
  videoUrl: string | null;
  videoId: string | null;
  taskId: string | null;
  error: string | null;
  size?: string;
  seconds?: string;
  modelKey?: VideoModelKey;
}

export interface HistoryItem {
  id: string;
  keyIndex: number;
  createdAt: number;
  promptPreview: string;
  modelKey?: VideoModelKey;
  modelName?: string;
  mode: GenMode;
  ratio: Ratio;
  resolution: ResolutionTier;
  status: TaskStatus;
  progress: number;
  videoUrl: string | null;
  videoId: string | null;
  taskId: string | null;
  error?: string | null;
  size?: string;
  seconds?: string;
}

export interface CreateVideoTaskResponse {
  id?: string;
  task_id?: string;
  video_id?: string;
  object?: string;
  model?: string;
  status?: string;
  progress?: number;
  created_at?: number;
  seconds?: string;
  size?: string;
  error?: { message?: string };
}

export interface VideoResultResponse {
  id?: string;
  video_id?: string;
  task_id?: string;
  model?: string;
  object?: string;
  status?: string;
  progress?: number;
  created_at?: number;
  completed_at?: number;
  seconds?: string;
  size?: string;
  metadata?: {
    url?: string;
    size_mapping?: Record<string, unknown>;
  };
  error?: { message?: string } | null;
}
