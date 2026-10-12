import { SNOW_DIRECTOR_AVOID } from './negativePrompt';
import type {
  DurationPresetKey,
  GenerationParams,
  Ratio,
  ResolutionTier,
  VideoModelKey,
} from './types';

export const API_BASE = 'https://apihub.agnes-ai.com';

// 8-shot/46s MYCL-001 is frozen; this only fills the already-approved first shot.
export const MYCL001_SHOT1_FROZEN_PROMPT = "handmade needle-felt stop-motion miniature diorama, visible wool fiber texture, soft warm studio light, shallow depth of field, tactile handmade feel. needle-felted American Shorthair cat, silver tabby with dark classic swirl markings, round amber eyes, tiny white lab coat with two buttons, visible wool fiber texture, handmade miniature puppet. medium shot, cat centered, bowl in lower third; sitting upright beside a small ceramic water bowl, looking straight at camera, ears forward; miniature felt kitchen counter, tiny felt window with warm morning light behind. the felt cat sits still beside the bowl, blinks once slowly, then tilts its head toward the camera. slow push in. medium shot, same framing, slightly closer; head tilted to one side, eyes half closed mid-blink, chin visibly dry and clean; same felt kitchen counter, same warm light";

// Test-only: the pinned public reference image does NOT contain the approved water bowl.
export const MYCL001_PUBLIC_I2V_TEST_PROMPT =
  'A handmade needle-felted silver tabby cat puppet with amber eyes and a miniature white lab coat. ' +
  'Animate ONLY the existing pose from the supplied first frame: one gentle blink, tiny head tilt, and subtle breathing. ' +
  'Preserve the exact felt fibers, background, composition, face pattern and clothing. Keep the camera steady. ' +
  'Do not introduce a water bowl or other new objects. This is a supplier image-to-video pathway test, not the approved first shot.';

// Internal experiment only: reference identity is NOT an approved frame or commercial asset.
export const MYCL001_CHARACTER_REFERENCE_URL = 'https://raw.githubusercontent.com/wpuu/AniFlow/4a09aa3d93f25f753c3379fd8bf4501427a266a0/assets/character/agnes-felt-test-frame.png';
export const MYCL001_SHOT1_REFERENCE_PROMPT =
  'Use <Picture 1> only as a character reference: preserve the silver tabby face, amber eyes and white lab coat. Do NOT copy the standing pose, left-side appliance, or missing bowl in the source image. ' + MYCL001_SHOT1_FROZEN_PROMPT;

// Only documented current video models are selectable; v2 is kept solely to display legacy history.
export const SELECTABLE_VIDEO_MODELS = ['flash25', 'paid25'] as const;

export const VIDEO_MODELS: Record<
  VideoModelKey,
  { label: string; apiModel: string; description: string }
> = {
  v2: {
    label: 'Agnes Video V2.0',
    apiModel: 'agnes-video-v2.0',
    description: '旧版记录兼容查看，已从可选模型移除',
  },
  flash25: {
    label: 'Flash',
    apiModel: 'agnes-video-2.5-flash',
    description: '720P · 官方当前限时 $0/秒；价格可变化，支持文生/首尾帧/参考图',
  },
  paid25: {
    label: 'Agnes Video 2.5 · 付费',
    apiModel: 'agnes-video-2.5',
    description: '720P $0.025/秒、1080P $0.040/秒；每次生成前确认费用',
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
  if (modelKey !== 'v2') {
    return [
      { value: 't2v', label: '文生视频', desc: '2.5 Flash text 模式' },
      { value: 'i2v', label: '单图生视频', desc: '使用首帧 first_frame 让图片动起来' },
      { value: 'keyframes', label: '首尾帧动画', desc: '使用 first_frame + last_frame 控制过渡' },
      { value: 'reference', label: '角色参考图', desc: '参考已有角色外观，不固定首帧构图；画质及权利仍须核实' },
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
  negativePrompt: SNOW_DIRECTOR_AVOID,
  keyframeScenes: [
    { id: 'flash-first', imageUrl: '', fileName: '' },
    { id: 'flash-last', imageUrl: '', fileName: '' },
  ],
};

export const DEFAULT_PARAMS_BY_MODEL: Record<VideoModelKey, GenerationParams> = {
  v2: DEFAULT_PARAMS_V2,
  flash25: DEFAULT_PARAMS_FLASH25,
  paid25: { ...DEFAULT_PARAMS_FLASH25, resolution: '720p' },
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
  submission_unknown: '未收到编号·可重试',
};

export const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-zinc-100 text-zinc-500',
  creating: 'bg-amber-100 text-amber-700',
  queued: 'bg-amber-100 text-amber-700',
  in_progress: 'bg-sky-100 text-sky-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
  stopped: 'bg-zinc-200 text-zinc-600',
  submission_unknown: 'bg-amber-100 text-amber-800',
};
