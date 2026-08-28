import { DURATION_PRESETS, MODE_OPTIONS, RESOLUTION_OPTIONS, RESOLUTION_PRESETS } from '../lib/constants';
import type { GenerationParams } from '../lib/types';
import { clampNumFrames } from '../lib/api';
import RatioSelector from './RatioSelector';
import KeyframeManager from './KeyframeManager';
import ImageUploadSlot from './ImageUploadSlot';
import CollapsibleSection from './CollapsibleSection';
import { cn } from '../utils/cn';
import { useRef } from 'react';

interface Props {
  params: GenerationParams;
  onChange: (updater: (prev: GenerationParams) => GenerationParams) => void;
}

export default function SettingsForm({ params, onChange }: Props) {
  const negRef = useRef<HTMLTextAreaElement>(null);

  function setMode(mode: GenerationParams['mode']) {
    onChange((prev) => ({ ...prev, mode }));
  }

  function setRatio(ratio: GenerationParams['ratio']) {
    onChange((prev) => {
      const [w, h] = RESOLUTION_PRESETS[prev.resolution][ratio];
      return { ...prev, ratio, width: w, height: h };
    });
  }

  function setResolution(resolution: GenerationParams['resolution']) {
    onChange((prev) => {
      const [w, h] = RESOLUTION_PRESETS[resolution][prev.ratio];
      return { ...prev, resolution, width: w, height: h };
    });
  }

  function setDurationPreset(key: GenerationParams['durationPreset']) {
    onChange((prev) => {
      const preset = DURATION_PRESETS.find((p) => p.key === key)!;
      if (key === 'custom') {
        return { ...prev, durationPreset: key };
      }
      return { ...prev, durationPreset: key, numFrames: preset.numFrames, frameRate: preset.frameRate };
    });
  }

  return (
    <div className="space-y-4">
      {/* 生成模式 */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">生成模式</h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {MODE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setMode(opt.value)}
              className={cn(
                'rounded-lg border px-3 py-2.5 text-left transition',
                params.mode === opt.value
                  ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500'
                  : 'border-zinc-200 hover:border-zinc-300',
              )}
            >
              <p className="text-sm font-semibold text-zinc-800">{opt.label}</p>
              <p className="mt-0.5 text-[11px] text-zinc-400">{opt.desc}</p>
            </button>
          ))}
        </div>

        {params.mode === 'i2v' ? (
          <div className="mt-3">
            <ImageUploadSlot
              label="待生成动画的图片"
              imageUrl={params.singleImage}
              fileName={params.singleImageFileName}
              onChange={(url, fileName) =>
                onChange((prev) => ({ ...prev, singleImage: url, singleImageFileName: fileName }))
              }
            />
          </div>
        ) : null}

        {params.mode === 'keyframes' ? (
          <div className="mt-3">
            <KeyframeManager
              scenes={params.keyframeScenes}
              onChange={(scenes) => onChange((prev) => ({ ...prev, keyframeScenes: scenes }))}
            />
          </div>
        ) : null}
      </div>

      {/* 提示词 */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-zinc-800">提示词</h3>
        <textarea
          value={params.prompt}
          onChange={(e) => onChange((prev) => ({ ...prev, prompt: e.target.value }))}
          placeholder="描述你想要生成的视频画面、镜头运动、光线氛围等，例如：镜头缓缓推近，女子转身望向镜头，海边落日余晖，电影级光效"
          rows={4}
          className="w-full resize-none rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
      </div>

      {/* 画面比例 */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">画面比例</h3>
        <RatioSelector value={params.ratio} onChange={setRatio} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-zinc-500">分辨率档位：</span>
          {RESOLUTION_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setResolution(opt.value)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition',
                params.resolution === opt.value
                  ? 'border-indigo-500 bg-indigo-600 text-white'
                  : 'border-zinc-300 text-zinc-500 hover:border-zinc-400',
              )}
            >
              {opt.label}
            </button>
          ))}
          <span className="ml-auto text-xs text-zinc-400">
            输出尺寸：{params.width} × {params.height}
          </span>
        </div>
      </div>

      {/* 视频时长 */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">视频时长</h3>
        <div className="flex flex-wrap gap-2">
          {DURATION_PRESETS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setDurationPreset(opt.key)}
              className={cn(
                'rounded-full border px-3 py-1.5 text-xs font-medium transition',
                params.durationPreset === opt.key
                  ? 'border-indigo-500 bg-indigo-600 text-white'
                  : 'border-zinc-300 text-zinc-500 hover:border-zinc-400',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {params.durationPreset === 'custom' ? (
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="text-xs text-zinc-500">
              帧数 num_frames（≤441，8n+1）
              <input
                type="number"
                value={params.numFrames}
                onChange={(e) =>
                  onChange((prev) => ({ ...prev, numFrames: clampNumFrames(Number(e.target.value) || 1) }))
                }
                className="mt-1 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-indigo-500"
              />
            </label>
            <label className="text-xs text-zinc-500">
              帧率 frame_rate（1-60）
              <input
                type="number"
                min={1}
                max={60}
                value={params.frameRate}
                onChange={(e) =>
                  onChange((prev) => ({
                    ...prev,
                    frameRate: Math.min(60, Math.max(1, Number(e.target.value) || 1)),
                  }))
                }
                className="mt-1 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-indigo-500"
              />
            </label>
          </div>
        ) : (
          <p className="mt-2 text-[11px] text-zinc-400">
            num_frames: {params.numFrames}，frame_rate: {params.frameRate}
          </p>
        )}
      </div>

      {/* 高级设置（不常用功能折叠） */}
      <CollapsibleSection title="高级设置" subtitle="反向提示词 / 推理步数 / 随机种子">
        <div className="space-y-3">
          <label className="block text-xs text-zinc-500">
            反向提示词 negative_prompt
            <textarea
              ref={negRef}
              value={params.negativePrompt}
              onChange={(e) => onChange((prev) => ({ ...prev, negativePrompt: e.target.value }))}
              placeholder="描述不希望出现的内容，例如：模糊、抖动、畸变、水印"
              rows={2}
              className="mt-1 w-full resize-none rounded-md border border-zinc-300 px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-zinc-500">
              推理步数 num_inference_steps
              <input
                type="number"
                value={params.numInferenceSteps}
                onChange={(e) =>
                  onChange((prev) => ({
                    ...prev,
                    numInferenceSteps: e.target.value === '' ? '' : Number(e.target.value),
                  }))
                }
                placeholder="默认"
                className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500"
              />
            </label>
            <label className="text-xs text-zinc-500">
              随机种子 seed
              <input
                type="number"
                value={params.seed}
                onChange={(e) =>
                  onChange((prev) => ({ ...prev, seed: e.target.value === '' ? '' : Number(e.target.value) }))
                }
                placeholder="随机"
                className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500"
              />
            </label>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
}
