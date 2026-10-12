import { useRef } from 'react';
import {
  DURATION_PRESETS,
  FLASH_SECONDS_PRESETS,
  MYCL001_SHOT1_FROZEN_PROMPT,
  MYCL001_SHOT1_REFERENCE_PROMPT,
  MYCL001_CHARACTER_REFERENCE_URL,
  RESOLUTION_OPTIONS,
  RESOLUTION_PRESETS,
  VIDEO_MODELS,
  SELECTABLE_VIDEO_MODELS,
  modeOptions,
} from '../lib/constants';
import type { GenerationParams, VideoModelKey } from '../lib/types';
import { clampFlashSeconds, clampNumFrames } from '../lib/api';
import RatioSelector from './RatioSelector';
import KeyframeManager from './KeyframeManager';
import ImageUploadSlot from './ImageUploadSlot';
import CollapsibleSection from './CollapsibleSection';
import { cn } from '../utils/cn';

interface Props {
  modelKey: VideoModelKey;
  onModelChange: (modelKey: VideoModelKey) => void;
  params: GenerationParams;
  onChange: (updater: (prev: GenerationParams) => GenerationParams) => void;
}

export default function SettingsForm({ modelKey, onModelChange, params, onChange }: Props) {
  const negRef = useRef<HTMLTextAreaElement>(null);
  const modes = modeOptions(modelKey);
  const isFlash = modelKey === 'flash25';
  const isModern = modelKey !== 'v2';

  function setMode(mode: GenerationParams['mode']) {
    onChange((prev) => ({ ...prev, mode }));
  }

  function setRatio(ratio: GenerationParams['ratio']) {
    onChange((prev) => {
      const resolution = isFlash ? '720p' : prev.resolution;
      const [w, h] = RESOLUTION_PRESETS[resolution][ratio];
      return { ...prev, ratio, resolution, width: w, height: h };
    });
  }

  function setResolution(resolution: GenerationParams['resolution']) {
    if (isFlash) return;
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

  function setFlashFrame(index: number, imageUrl: string, fileName?: string) {
    onChange((prev) => {
      const scenes = [...prev.keyframeScenes];
      while (scenes.length < 2) {
        scenes.push({ id: `flash-${scenes.length}`, imageUrl: '', fileName: '' });
      }
      scenes[index] = { ...scenes[index], imageUrl, fileName };
      return { ...prev, keyframeScenes: scenes.slice(0, 2) };
    });
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">视频模型</h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {SELECTABLE_VIDEO_MODELS.map((key) => {
            const model = VIDEO_MODELS[key];
            return (
              <button
                key={key}
                type="button"
                onClick={() => onModelChange(key)}
                className={cn(
                  'rounded-lg border px-3 py-2.5 text-left transition',
                  modelKey === key
                    ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500'
                    : 'border-zinc-200 hover:border-zinc-300',
                )}
              >
                <p className="text-sm font-semibold text-zinc-800">{model.label}</p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-zinc-400">{model.description}</p>
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] text-zinc-400">
          两个模型分别保存自己的参数；切换模型不会重置另一套设置。
        </p>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">生成模式</h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {modes.map((opt) => (
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

        {(params.mode === 'i2v' || (isModern && params.mode === 'reference')) ? (
          <div className="mt-3">
            <ImageUploadSlot
              label={isModern && params.mode === 'reference' ? '角色参考图片（images[0]；不固定首帧）' : isModern ? '首帧图片（first_frame）' : '待生成动画的图片'}
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
            {isModern ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <ImageUploadSlot
                  label="首帧（first_frame）"
                  imageUrl={params.keyframeScenes[0]?.imageUrl ?? ''}
                  fileName={params.keyframeScenes[0]?.fileName}
                  onChange={(url, fileName) => setFlashFrame(0, url, fileName)}
                  compact
                />
                <ImageUploadSlot
                  label="尾帧（last_frame）"
                  imageUrl={params.keyframeScenes[1]?.imageUrl ?? ''}
                  fileName={params.keyframeScenes[1]?.fileName}
                  onChange={(url, fileName) => setFlashFrame(1, url, fileName)}
                  compact
                />
              </div>
            ) : (
              <KeyframeManager
                scenes={params.keyframeScenes}
                onChange={(scenes) => onChange((prev) => ({ ...prev, keyframeScenes: scenes }))}
              />
            )}
          </div>
        ) : null}
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-zinc-800">提示词</h3>
        {isModern ? (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button type="button" className="rounded-md border border-indigo-500 px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-indigo-50"
              onClick={() => {
                if (params.prompt.trim() && params.prompt !== MYCL001_SHOT1_FROZEN_PROMPT
                  && !window.confirm('会替换当前提示词与画面设置，但不会提交视频。确认载入 MYCL-001 第一镜头？')) return;
                onChange((prev) => ({
                  ...prev,
                  prompt: MYCL001_SHOT1_FROZEN_PROMPT,
                  mode: 't2v',
                  ratio: '9:16',
                  resolution: '720p',
                  width: 720,
                  height: 1280,
                  seconds: 5,
                }));
              }}>
              载入雪所长首镜头 · 5秒
            </button>
            <button type="button" className="rounded-md border border-amber-500 px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-50"
              onClick={() => {
                if (params.prompt.trim() && params.prompt !== MYCL001_SHOT1_REFERENCE_PROMPT
                  && !window.confirm('载入角色参考图试验参数，仅用于测试一致性，不会提交视频。确认继续？')) return;
                onChange((prev) => ({
                  ...prev,
                  prompt: MYCL001_SHOT1_REFERENCE_PROMPT,
                  mode: 'reference',
                  singleImage: MYCL001_CHARACTER_REFERENCE_URL,
                  singleImageFileName: '',
                  ratio: '9:16',
                  resolution: '720p',
                  width: 720,
                  height: 1280,
                  seconds: 5,
                }));
              }}>
              载入角色参考图测试 · 5秒
            </button>
            <span className="text-[11px] text-zinc-400">按钮只填参数；参考图不是合格首帧，也未完成商用权利核实</span>
          </div>
        ) : null}
        <textarea
          value={params.prompt}
          onChange={(e) => onChange((prev) => ({ ...prev, prompt: e.target.value }))}
          placeholder="描述画面、动作、镜头、光线与风格。"
          rows={4}
          className="w-full resize-none rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">画面比例</h3>
        <RatioSelector value={params.ratio} onChange={setRatio} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-zinc-500">分辨率：</span>
          {isFlash ? (
            <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-600">
              720P（2.5 Flash 固定）
            </span>
          ) : (
            RESOLUTION_OPTIONS.filter((opt) => isModern ? opt.value !== '480p' : true).map((opt) => (
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
            ))
          )}
          <span className="ml-auto text-xs text-zinc-400">
            输出尺寸：{params.width} × {params.height}
          </span>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-800">视频时长</h3>
        {isModern ? (
          <>
            <div className="flex flex-wrap gap-2">
              {FLASH_SECONDS_PRESETS.map((seconds) => (
                <button
                  key={seconds}
                  type="button"
                  onClick={() => onChange((prev) => ({ ...prev, seconds }))}
                  className={cn(
                    'rounded-full border px-3 py-1.5 text-xs font-medium transition',
                    params.seconds === seconds
                      ? 'border-indigo-500 bg-indigo-600 text-white'
                      : 'border-zinc-300 text-zinc-500 hover:border-zinc-400',
                  )}
                >
                  {seconds} 秒
                </button>
              ))}
            </div>
            <label className="mt-3 block max-w-52 text-xs text-zinc-500">
              自定义 seconds（4–12）
              <input
                type="number"
                min={4}
                max={12}
                value={params.seconds}
                onChange={(e) =>
                  onChange((prev) => ({ ...prev, seconds: clampFlashSeconds(Number(e.target.value)) }))
                }
                className="mt-1 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-indigo-500"
              />
            </label>
          </>
        ) : (
          <>
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
          </>
        )}
      </div>

      <CollapsibleSection
        title="高级设置"
        subtitle={isModern ? '随机种子' : '反向提示词 / 推理步数 / 随机种子'}
      >
        <div className="space-y-3">
          {!isModern ? (
            <>
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
              <label className="block text-xs text-zinc-500">
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
            </>
          ) : null}
          <label className="block text-xs text-zinc-500">
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
      </CollapsibleSection>
    </div>
  );
}
