import { useEffect, useState } from 'react';
import {
  DEFAULT_BRIDGE_URL,
  generateImageThroughBridge,
  getBridgeHealth,
  uploadDataUrlToBridge,
  type BridgeHealth,
} from '../lib/bridge';
import { STORAGE_KEYS, loadJSON, saveJSON } from '../lib/storage';
import ImageUploadSlot from './ImageUploadSlot';
import { cn } from '../utils/cn';

type ImageProviderKey = 'agnes' | 'capcut';
type FrameTarget = 'single' | 'first' | 'last';

interface ReferenceImage {
  imageUrl: string;
  fileName?: string;
}

interface Props {
  apiKeys: string[];
  onUseResult: (url: string, target: FrameTarget) => void;
}

function createEmptyReferences(): ReferenceImage[] {
  return Array.from({ length: 3 }, () => ({ imageUrl: '', fileName: '' }));
}

function isPublicUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
}

export default function ImageGeneratorPanel({ apiKeys, onUseResult }: Props) {
  const [provider, setProvider] = useState<ImageProviderKey>(() =>
    loadJSON<ImageProviderKey>(STORAGE_KEYS.IMAGE_PROVIDER, 'capcut'),
  );
  const [capcutModel, setCapcutModel] = useState(() =>
    loadJSON<string>(STORAGE_KEYS.CAPCUT_IMAGE_MODEL, ''),
  );
  const [prompt, setPrompt] = useState(() => loadJSON<string>(STORAGE_KEYS.IMAGE_PROMPT, ''));
  const [ratio, setRatio] = useState('9:16');
  const [keyIndex, setKeyIndex] = useState(0);
  const [references, setReferences] = useState<ReferenceImage[]>(createEmptyReferences);
  const [health, setHealth] = useState<BridgeHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.IMAGE_PROVIDER, provider);
  }, [provider]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.CAPCUT_IMAGE_MODEL, capcutModel);
  }, [capcutModel]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.IMAGE_PROMPT, prompt);
  }, [prompt]);

  useEffect(() => {
    void refreshHealth();
  }, []);

  async function refreshHealth() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 2500);
    try {
      const next = await getBridgeHealth(DEFAULT_BRIDGE_URL, controller.signal);
      setHealth(next);
      setHealthError(null);
      if (!capcutModel && next.capcut_model) setCapcutModel(next.capcut_model);
    } catch {
      setHealth(null);
      setHealthError('本机 Bridge 未连接');
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function updateReference(index: number, imageUrl: string, fileName?: string) {
    setReferences((prev) =>
      prev.map((item, i) => (i === index ? { imageUrl, fileName } : item)),
    );
  }

  async function resolveReference(value: string): Promise<string> {
    const trimmed = value.trim();
    if (isPublicUrl(trimmed)) return trimmed;
    if (trimmed.startsWith('data:image/')) {
      const uploaded = await uploadDataUrlToBridge(trimmed, DEFAULT_BRIDGE_URL);
      return uploaded.url;
    }
    throw new Error('参考图必须是本地上传图片或 http(s) 图片 URL');
  }

  async function generate() {
    if (!prompt.trim()) {
      setError('请先填写生图提示词');
      return;
    }
    const apiKey = apiKeys[keyIndex]?.trim();
    if (provider === 'agnes' && !apiKey) {
      setError(`Agnes Image 需要先填写 Key ${keyIndex + 1}`);
      return;
    }
    if (provider === 'capcut' && !capcutModel.trim()) {
      setError('请填写当前 CapCut 页面实际使用的 Seedream 模型名称');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const referenceUrls = await Promise.all(
        references
          .map((item) => item.imageUrl)
          .filter((value) => value.trim())
          .map(resolveReference),
      );
      const result = await generateImageThroughBridge(
        {
          provider,
          prompt: prompt.trim(),
          references: referenceUrls,
          ratio,
          size: '1K',
          api_key: provider === 'agnes' ? apiKey : undefined,
          model: provider === 'capcut' ? capcutModel.trim() : undefined,
        },
        DEFAULT_BRIDGE_URL,
      );
      setResultUrl(result.url);
      await refreshHealth();
    } catch (err) {
      setError(err instanceof Error ? err.message : '生图失败');
    } finally {
      setLoading(false);
    }
  }

  const capcutRunnerUnavailable =
    provider === 'capcut' && health !== null && !health.capcut_runner_ready;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-zinc-50 px-3 py-2">
        <div className="flex items-center gap-2 text-xs">
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              health ? (health.media_ready ? 'bg-emerald-500' : 'bg-amber-500') : 'bg-zinc-300',
            )}
          />
          <span className="text-zinc-600">
            {health
              ? health.media_ready
                ? 'AniFlow Bridge 已连接 · 公网媒体可用'
                : 'AniFlow Bridge 已连接 · 尚未配置 R2/S3'
              : healthError || '正在检查 AniFlow Bridge…'}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void refreshHealth()}
          className="text-xs font-medium text-indigo-600 hover:underline"
        >
          重新检查
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => setProvider('capcut')}
          className={cn(
            'rounded-lg border px-3 py-3 text-left transition',
            provider === 'capcut'
              ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
              : 'border-zinc-200 hover:border-zinc-300',
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-zinc-800">CapCut / Seedream</span>
            {health?.capcut_runner_ready ? (
              <span className="text-[10px] font-medium text-emerald-600">Agent Runner 已配置</span>
            ) : null}
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">浏览器 Agent 控制 CapCut 正常页面，支持参考图</p>
        </button>
        <button
          type="button"
          onClick={() => setProvider('agnes')}
          className={cn(
            'rounded-lg border px-3 py-3 text-left transition',
            provider === 'agnes'
              ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
              : 'border-zinc-200 hover:border-zinc-300',
          )}
        >
          <span className="text-sm font-semibold text-zinc-800">Agnes Image</span>
          <p className="mt-1 text-[11px] text-zinc-400">直接调用 Agnes Image，生成后自动持久化到媒体存储</p>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {provider === 'capcut' ? (
          <label className="text-xs text-zinc-500">
            CapCut 模型名称（页面填写并自动保存）
            <input
              value={capcutModel}
              onChange={(event) => setCapcutModel(event.target.value)}
              placeholder="例如 Seedream 4.3 / 4.0s / 5.0"
              className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-2 text-sm outline-none focus:border-indigo-500"
            />
          </label>
        ) : (
          <label className="text-xs text-zinc-500">
            使用 Agnes Key
            <select
              value={keyIndex}
              onChange={(event) => setKeyIndex(Number(event.target.value))}
              className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-2 text-sm outline-none focus:border-indigo-500"
            >
              {apiKeys.map((_, index) => (
                <option key={index} value={index}>
                  Key {index + 1}{apiKeys[index]?.trim() ? '' : '（未填写）'}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="text-xs text-zinc-500">
          画面比例
          <select
            value={ratio}
            onChange={(event) => setRatio(event.target.value)}
            className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-2 text-sm outline-none focus:border-indigo-500"
          >
            <option value="9:16">9:16 竖版</option>
            <option value="16:9">16:9 横版</option>
            <option value="1:1">1:1 方形</option>
            <option value="3:4">3:4 竖版</option>
            <option value="4:3">4:3 横版</option>
          </select>
        </label>
      </div>

      <label className="block text-xs text-zinc-500">
        生图提示词
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={4}
          placeholder="描述角色、场景、姿态、材质、镜头和需要保持的参考图特征"
          className="mt-1 w-full resize-y rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
      </label>

      <div>
        <p className="mb-2 text-xs font-medium text-zinc-600">参考图（可选，最多 3 张）</p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {references.map((item, index) => (
            <ImageUploadSlot
              key={index}
              label={`参考图 ${index + 1}`}
              imageUrl={item.imageUrl}
              fileName={item.fileName}
              onChange={(url, fileName) => updateReference(index, url, fileName)}
              compact
            />
          ))}
        </div>
      </div>

      {capcutRunnerUnavailable ? (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
          CapCut Agent Runner 尚未配置。模型名可以直接在本页面填写，不需要写进 .env；但本机仍需要配置浏览器 Agent Runner。
        </p>
      ) : null}

      {error ? <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</p> : null}

      <button
        type="button"
        onClick={() => void generate()}
        disabled={loading || !prompt.trim() || capcutRunnerUnavailable}
        className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? '正在生成…' : `使用 ${provider === 'capcut' ? 'CapCut / Seedream' : 'Agnes Image'} 生图`}
      </button>

      {resultUrl ? (
        <div className="grid grid-cols-1 gap-4 rounded-lg border border-emerald-200 bg-emerald-50/40 p-3 sm:grid-cols-[180px_1fr]">
          <div className="overflow-hidden rounded-lg bg-zinc-100">
            <img src={resultUrl} alt="AI generated result" className="h-full max-h-72 w-full object-contain" />
          </div>
          <div className="min-w-0 space-y-3">
            <div>
              <p className="text-xs font-semibold text-zinc-700">生成结果</p>
              <a
                href={resultUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 block truncate text-xs text-indigo-600 underline decoration-dotted"
              >
                {resultUrl}
              </a>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onUseResult(resultUrl, 'single')}
                className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
              >
                设为当前模型单图首帧
              </button>
              <button
                type="button"
                onClick={() => onUseResult(resultUrl, 'first')}
                className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
              >
                设为 2.5 Flash 首帧
              </button>
              <button
                type="button"
                onClick={() => onUseResult(resultUrl, 'last')}
                className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
              >
                设为 2.5 Flash 尾帧
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
