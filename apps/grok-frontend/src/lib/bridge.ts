export const DEFAULT_BRIDGE_URL = 'http://127.0.0.1:8765';

export interface BridgeHealth {
  ok: boolean;
  media_ready: boolean;
  capcut_ready: boolean;
  capcut_model?: string | null;
  bridge: string;
}

export interface BridgeUploadResult {
  url: string;
  object_key: string;
  size_bytes: number;
}

export interface BridgeGenerateImageRequest {
  provider: 'agnes' | 'capcut';
  prompt: string;
  references?: string[];
  ratio?: string;
  size?: string;
  api_key?: string;
  model?: string;
}

export interface BridgeGenerateImageResult {
  provider: 'agnes' | 'capcut';
  model: string;
  url: string;
}

function normalizeBridgeUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

async function readError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string };
    if (data?.detail) return data.detail;
  } catch {
    // fall through
  }
  return `HTTP ${res.status}`;
}

export async function getBridgeHealth(
  bridgeUrl = DEFAULT_BRIDGE_URL,
  signal?: AbortSignal,
): Promise<BridgeHealth> {
  const res = await fetch(`${normalizeBridgeUrl(bridgeUrl)}/api/health`, { signal });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BridgeHealth;
}

export async function uploadDataUrlToBridge(
  dataUrl: string,
  bridgeUrl = DEFAULT_BRIDGE_URL,
): Promise<BridgeUploadResult> {
  if (!dataUrl.startsWith('data:image/')) {
    throw new Error('仅支持上传浏览器中的图片 data URL');
  }

  const source = await fetch(dataUrl);
  const blob = await source.blob();
  const mime = blob.type || 'image/png';
  const extension = mime.includes('webp') ? 'webp' : mime.includes('jpeg') ? 'jpg' : 'png';
  const form = new FormData();
  form.append('file', blob, `aniflow-upload.${extension}`);

  let res: Response;
  try {
    res = await fetch(`${normalizeBridgeUrl(bridgeUrl)}/api/media/upload`, {
      method: 'POST',
      body: form,
    });
  } catch {
    throw new Error(
      `无法连接 AniFlow 本机 Bridge（${normalizeBridgeUrl(bridgeUrl)}）。请先启动 aniflow bridge。`,
    );
  }

  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BridgeUploadResult;
}

export async function generateImageThroughBridge(
  request: BridgeGenerateImageRequest,
  bridgeUrl = DEFAULT_BRIDGE_URL,
): Promise<BridgeGenerateImageResult> {
  let res: Response;
  try {
    res = await fetch(`${normalizeBridgeUrl(bridgeUrl)}/api/images/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
  } catch {
    throw new Error(
      `无法连接 AniFlow 本机 Bridge（${normalizeBridgeUrl(bridgeUrl)}）。请先启动 aniflow bridge。`,
    );
  }

  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BridgeGenerateImageResult;
}
