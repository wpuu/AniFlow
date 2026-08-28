import type {
  DurationPresetKey,
  GenerationParams,
  Ratio,
  ResolutionTier,
  VideoModelKey,
} from './types';

export const API_BASE = 'https://apihub.agnes-ai.com';

export const VIDEO_MODELS: Record<
  VideoModelKey,
  { label: string; apiModel: string; description: string }
> = {
  v2: {
    label: 'Agnes Video V2.0',
    apiModel: 'agnes-video-v2.0',
    description: '旧版高级参数完整，保留分辨率、帧数、帧率和多关键帧能力',
  },
  flash25: {
    label: 'Agnes Video 2.5 Flash',
    apiModel: 'agnes-video-2.5-flash',
    description: '新版 Flash 接口，720P，4–12 秒，支持文生视频、单图和首尾帧',
  },
};

export const RESOLUTION_PRESETS: Record<ResolutionTier, Record<Ratio, [number, number]>> = {
  '480p': {
    '16:9': [832, 448],
    '9:16': [448, 832],
    '1:1': [576, 576],
    '4:3': [736, 552],
    '3:4': [552, 736],
  },
  '720p': {
    '16:9': [1280, 720],
    '9:16': [720, 1280],
    '1:1': [720, 720],
    '4:3': [960, 720],
    '3:4': [720, 960],
  },
  '1080p': {
    '16:9': [1920, 1080],
    '9:16': [1080, 1920],
    '1:1': [1080, 1080],
    '4:3': [1440, 1080],
    '3:4': [1080, 1440],
  },
};

export const RATIO_OPTIONS: { value: Ratio; label: string; desc: string }[] = [
  { value: '9:16', label: '9:16', desc: '竖版短视频 · 抖音 / Reels / Shorts' },
  { value: '16:9', label: '16:9', desc: '横版视频 · 产品演示 / YouTube' },
  { value: '1:1', label: '1:1', desc: '方形视频 · 社交媒体信息流' },
  { value: '4:3', label: '4:3', desc: '传统横版 · 通用演示' },
  { value: '3:4', label: '3:4', desc: '竖版演示 · 肖像 / 产品展示' },
];

export const RESOLUTION_OPTIONS: { value: ResolutionTier; label: string }[] = [
  { value: '480p', label: '480p 标清' },
  { value: '720p', label: '720p 高清' },
  { value: '1080p', label: '1080p 超清' },
];

export const DURATION_PRESETS: {
  key: DurationPresetKey;
  label: string;
  numFrames: number;
  frameRate: number;
}[] = [
  { key: '3', label: '约 3 秒', numFrames: 81, frameRate: 24 },
  { key: '5', label: '约 5 秒', numFrames: 121, frameRate: 24 },
  { key: '10', label: '约 10 秒', numFrames: 241, frameRate: 24 },
  { key: '18', label: '约 18 秒', numFrames: 441, frameRate: 24 },
  { key: 'custom', label: '自定义', numFrames: 121, frameRate: 24 },
];

export const FLASH_SECONDS_PRESETS = [4, 5, 6, 8, 10, 12] as const;

export function modeOptions(modelKey: VideoModelKey): {
  value: GenerationParams['mode'];
  label: string;
  desc: string;
}[] {
  if (modelKey === 'flash25') {
    return [
      { value: 't2v', label: '文生视频', desc: '2.5 Flash text 模式' },
      { value: 'i2v', label: '单图生视频', desc: '使用首帧 first_frame 让图片动起来' },
      { value: 'keyframes', label: '首尾帧动画', desc: '使用 first_frame + last_frame 控制过渡' },
    ];
  }
  return [
    { value: 't2v', label: '文生视频', desc: '仅通过文字提示词生成视频' },
    { value: 'i2v', label: '图生视频', desc: '上传一张图片，让画面动起来' },
    { value: 'keyframes', label: '多关键帧动画', desc: '上传多张关键帧图片，生成过渡动画' },
  ];
}

export const MAX_NUM_FRAMES = 441;

export const DEFAULT_PARAMS_V2: GenerationParams = {
  mode: 't2v',
  prompt: '',
  negativePrompt: '',
  ratio: '9:16',
  resolution: '720p',
  width: RESOLUTION_PRESETS['720p']['9:16'][0],
  height: RESOLUTION_PRESETS['720p']['9:16'][1],
  durationPreset: '5',
  numFrames: 121,
  frameRate: 24,
  seconds: 5,
  numInferenceSteps: '',
  seed: '',
  singleImage: '',
  singleImageFileName: '',
  keyframeScenes: [
    { id: 'scene-1', imageUrl: '', fileName: '' },
    { id: 'scene-2', imageUrl: '', fileName: '' },
  ],
};

export const DEFAULT_PARAMS_FLASH25: GenerationParams = {
  ...DEFAULT_PARAMS_V2,
  mode: 't2v',
  resolution: '720p',
  width: 720,
  height: 1280,
  seconds: 5,
  keyframeScenes: [
    { id: 'flash-first', imageUrl: '', fileName: '' },
    { id: 'flash-last', imageUrl: '', fileName: '' },
  ],
};

export const DEFAULT_PARAMS_BY_MODEL: Record<VideoModelKey, GenerationParams> = {
  v2: DEFAULT_PARAMS_V2,
  flash25: DEFAULT_PARAMS_FLASH25,
};

// Backward compatibility for the imported Grok frontend.
export const DEFAULT_PARAMS = DEFAULT_PARAMS_V2;

export const STATUS_LABELS: Record<string, string> = {
  idle: '未开始',
  creating: '正在创建任务',
  queued: '排队中',
  in_progress: '生成中',
  completed: '已完成',
  failed: '失败',
  stopped: '已停止跟踪',
};

export const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-zinc-100 text-zinc-500',
  creating: 'bg-amber-100 text-amber-700',
  queued: 'bg-amber-100 text-amber-700',
  in_progress: 'bg-sky-100 text-sky-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
  stopped: 'bg-zinc-200 text-zinc-600',
};
