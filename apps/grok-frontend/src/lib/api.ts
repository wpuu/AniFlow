import { API_BASE, MAX_NUM_FRAMES, VIDEO_MODELS } from './constants';
import type {
  CreateVideoTaskResponse,
  GenerationParams,
  VideoModelKey,
  VideoResultResponse,
} from './types';

export function clampNumFrames(value: number): number {
  const n = Math.max(0, Math.round((value - 1) / 8));
  const clamped = Math.min(n, Math.floor((MAX_NUM_FRAMES - 1) / 8));
  return clamped * 8 + 1;
}

export function clampFlashSeconds(value: number): number {
  return Math.min(12, Math.max(4, Math.round(value || 4)));
}

function validImages(params: GenerationParams): string[] {
  return params.keyframeScenes.map((scene) => scene.imageUrl.trim()).filter(Boolean);
}

export function buildRequestBody(
  modelKey: VideoModelKey,
  params: GenerationParams,
): Record<string, unknown> {
  const model = VIDEO_MODELS[modelKey].apiModel;

  if (modelKey === 'flash25') {
    const body: Record<string, unknown> = {
      model,
      prompt: params.prompt.trim(),
      seconds: String(clampFlashSeconds(params.seconds)),
      size: '720P',
      aspect_ratio: params.ratio,
      n: 1,
    };

    if (params.mode === 't2v') {
      body.mode = 'text';
    } else if (params.mode === 'i2v') {
      body.mode = 'keyframe';
      if (params.singleImage) body.first_frame = params.singleImage;
    } else {
      const images = validImages(params);
      body.mode = 'keyframe';
      if (images[0]) body.first_frame = images[0];
      if (images[1]) body.last_frame = images[1];
    }

    if (params.seed !== '' && params.seed !== null && params.seed !== undefined) {
      body.seed = Number(params.seed);
    }
    return body;
  }

  const body: Record<string, unknown> = {
    model,
    prompt: params.prompt.trim(),
    width: params.width,
    height: params.height,
    num_frames: params.numFrames,
    frame_rate: params.frameRate,
  };

  if (params.negativePrompt.trim()) {
    body.negative_prompt = params.negativePrompt.trim();
  }
  if (params.numInferenceSteps !== '' && params.numInferenceSteps !== null && params.numInferenceSteps !== undefined) {
    body.num_inference_steps = Number(params.numInferenceSteps);
  }
  if (params.seed !== '' && params.seed !== null && params.seed !== undefined) {
    body.seed = Number(params.seed);
  }

  if (params.mode === 'i2v') {
    if (params.singleImage) {
      body.image = params.singleImage;
    }
    body.mode = 'ti2vid';
  } else if (params.mode === 'keyframes') {
    const images = validImages(params);
    body.extra_body = { image: images, mode: 'keyframes' };
  }

  return body;
}

async function parseJsonSafe(res: Response): Promise<Record<string, unknown> | null> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function apiError(data: Record<string, unknown> | null, fallback: string): Error {
  const message =
    (data?.error as { message?: string } | undefined)?.message ||
    (data?.message as string | undefined) ||
    fallback;
  return new Error(message);
}

export async function createVideoTask(
  apiKey: string,
  modelKey: VideoModelKey,
  params: GenerationParams,
): Promise<CreateVideoTaskResponse> {
  const res = await fetch(`${API_BASE}/v1/videos`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(buildRequestBody(modelKey, params)),
  });
  const data = await parseJsonSafe(res);
  if (!res.ok) {
    throw apiError(data, `创建任务失败（状态码 ${res.status}）`);
  }
  return (data || {}) as CreateVideoTaskResponse;
}

export async function getVideoResult(
  apiKey: string,
  videoId: string,
  modelKey: VideoModelKey,
): Promise<VideoResultResponse> {
  const modelName = VIDEO_MODELS[modelKey].apiModel;
  const url = `${API_BASE}/agnesapi?video_id=${encodeURIComponent(videoId)}&model_name=${encodeURIComponent(
    modelName,
  )}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  const data = await parseJsonSafe(res);
  if (!res.ok) {
    throw apiError(data, `查询结果失败（状态码 ${res.status}）`);
  }
  return (data || {}) as VideoResultResponse;
}
