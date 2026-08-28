import { API_BASE, MAX_NUM_FRAMES, MODEL_NAME } from './constants';
import type { CreateVideoTaskResponse, GenerationParams, VideoResultResponse } from './types';

export function clampNumFrames(value: number): number {
  const n = Math.max(0, Math.round((value - 1) / 8));
  const clamped = Math.min(n, Math.floor((MAX_NUM_FRAMES - 1) / 8));
  return clamped * 8 + 1;
}

export function buildRequestBody(params: GenerationParams): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: MODEL_NAME,
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
    const images = params.keyframeScenes.map((s) => s.imageUrl).filter(Boolean);
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

export async function createVideoTask(
  apiKey: string,
  params: GenerationParams,
): Promise<CreateVideoTaskResponse> {
  const res = await fetch(`${API_BASE}/v1/videos`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(buildRequestBody(params)),
  });
  const data = await parseJsonSafe(res);
  if (!res.ok) {
    const message =
      (data?.error as { message?: string } | undefined)?.message ||
      (data?.message as string | undefined) ||
      `创建任务失败（状态码 ${res.status}）`;
    throw new Error(message);
  }
  return (data || {}) as CreateVideoTaskResponse;
}

export async function getVideoResult(apiKey: string, videoId: string): Promise<VideoResultResponse> {
  const url = `${API_BASE}/agnesapi?video_id=${encodeURIComponent(videoId)}&model_name=${encodeURIComponent(
    MODEL_NAME,
  )}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  const data = await parseJsonSafe(res);
  if (!res.ok) {
    const message =
      (data?.error as { message?: string } | undefined)?.message ||
      (data?.message as string | undefined) ||
      `查询结果失败（状态码 ${res.status}）`;
    throw new Error(message);
  }
  return (data || {}) as VideoResultResponse;
}
