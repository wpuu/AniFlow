import type { Model, RealProvider, Task } from "./types";
// Only a local simulator is visible: no real AWS, Agnes or GPU is connected.
export const MODELS: Model[] = [{
  id: "mock-h3", name: "H3 模拟节点", shortName: "Mock H3",
  backend: "minimax", backendLabel: "本机 MOCK · 无GPU",
  status: "ready", latencyMs: 0, costPerSecond: 0, maxDuration: 10,
  description: "仅测试上传、队列、任务恢复和本地MP4。不是AI生成。",
  queue: 0, tags: ["模拟", "本机", "零费用"],
}];
export const REAL_MODEL: Model = {
  id: "minimax-h3", name: "MiniMax H3 · 真实节点", shortName: "H3 REAL",
  backend: "minimax", backendLabel: "AWS 私有连接 · ComfyUI",
  status: "offline", latencyMs: 0, costPerSecond: 0, maxDuration: 5,
  description: "真实图生视频；资格与停机保护未通过时禁止提交。",
  queue: 0, tags: ["真实", "5秒", "9:16"],
};
export const WAN_MODEL: Model = {
  id: "wan2.2-i2v-a14b", name: "Wan2.2 I2V A14B · 真实节点", shortName: "Wan2.2 REAL",
  backend: "huggingface", backendLabel: "AWS 俄亥俄州 · EC2 · ComfyUI",
  status: "offline", latencyMs: 0, costPerSecond: 0, maxDuration: 5,
  description: "真实图生视频候选；资格、原生规格与停机保护未通过时禁止提交。",
  queue: 0, tags: ["真实", "5秒", "9:16"],
};
const UNKNOWN_REAL_MODEL: Model = {
  ...REAL_MODEL, id: "unverified-real", name: "真实模型待核验", shortName: "真实模型待核验",
  backendLabel: "本机真实服务 · 身份未确认", description: "等待核验本机服务的真实模型身份。",
};
export function getRealModel(provider: RealProvider | null): Model {
  return provider === "minimax-h3" ? REAL_MODEL : provider === "wan2.2-i2v-a14b" ? WAN_MODEL : UNKNOWN_REAL_MODEL;
}
export const ASPECTS: { id: Task["aspectRatio"]; label: string; w: number; h: number }[] = [
  { id: "9:16", label: "竖屏", w: 9, h: 16 },
  { id: "16:9", label: "横屏", w: 16, h: 9 },
  { id: "1:1", label: "方形", w: 1, h: 1 },
];
export const DURATIONS = [4, 5, 6, 8, 10];
export const SAMPLE_FRAMES: {url:string;label:string}[] = [];
export const PROMPT_PRESETS = [
  "针毡银虎斑猫研究员穿白大褂，轻轻眨眼、稍微歪头，保留原始毛毡纤维、面部花纹和构图，镜头固定。",
  "毛毡风格的小猫安静地向前看，只有轻微呼吸与耳朵动作，避免塑料和写实真猫质感。",
];
export const INITIAL_TASKS: Task[] = [];
export function getModel(id: string): Model | undefined { return [...MODELS, REAL_MODEL, WAN_MODEL, UNKNOWN_REAL_MODEL].find(m=>m.id===id); }
