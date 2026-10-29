import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ChevronDown,
  Clapperboard,
  ImagePlus,
  Sparkles,
  X,
} from "lucide-react";
import { ASPECTS, DURATIONS, MODELS, PROMPT_PRESETS, SAMPLE_FRAMES, getModel, getRealModel } from "../data";
import type { AspectRatio, CreatePayload, Model, RealProvider, StudioMode } from "../types";
import { cn } from "../utils/cn";
import { formatCost } from "../utils/format";
import { ModelDot } from "./StatusBadge";
import { formatExpectedHardware, parseCloudPreflight } from "./AwsPreflightPanel";

interface CreatePanelProps {
  onSubmit: (payload: CreatePayload) => void;
  busyCount: number;
  disabled?: boolean;
  mode: StudioMode;
  realProvider: RealProvider | null;
  ready?: boolean;
}

export function CreatePanel({ onSubmit, busyCount, disabled = false, mode, realProvider, ready = false }: CreatePanelProps) {
  const real = mode === "real";
  const models: Model[] = real ? [{...getRealModel(realProvider),
    status: ready && realProvider !== null ? "ready" : "offline"}] : MODELS;
  const [hardwareLabel, setHardwareLabel] = useState<string | null>(null);
  const [prompt, setPrompt] = useState(PROMPT_PRESETS[0]);
  const [negativePrompt, setNegativePrompt] = useState("抖动, 过曝, 文字水印, 畸变, 低清晰度");
  const [modelId, setModelId] = useState(MODELS[0].id);
  const [aspect, setAspect] = useState<AspectRatio>("9:16");
  const [duration, setDuration] = useState(5);
  const [firstFrame, setFirstFrame] = useState<string | undefined>(undefined);
  const [seed, setSeed] = useState(82914);
  const [cfg, setCfg] = useState(7.5);
  const [motion, setMotion] = useState(0.65);
  const [fps, setFps] = useState(24);
  const [advanced, setAdvanced] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const model = real ? models[0] : getModel(modelId)!;
  const clampedDuration = Math.min(duration, model.maxDuration);
  const estimate = useMemo(
    () => Number((model.costPerSecond * clampedDuration).toFixed(3)),
    [model, clampedDuration],
  );

  function onFile(file?: File) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setFirstFrame(String(reader.result));
    reader.readAsDataURL(file);
  }

  function submit() {
    if (disabled || !prompt.trim() || !firstFrame?.startsWith("data:image/")) return;
    onSubmit({
      prompt,
      negativePrompt,
      modelId:model.id,
      aspectRatio: aspect,
      duration: clampedDuration,
      fps,
      seed,
      cfg,
      motion,
      firstFrame,
    });
  }

  useEffect(() => {
    let cancelled = false;
    setHardwareLabel(null);
    if (real && realProvider) {
      void fetch("/api/studio/cloud/preflight", {cache:"no-store"})
        .then(async response => {
          if (!response.ok) throw new Error("Hardware projection unavailable");
          const data = parseCloudPreflight(await response.json(), "real");
          if (data.provider !== realProvider) return;
          if (!cancelled) setHardwareLabel(formatExpectedHardware(data));
        }).catch(() => { if (!cancelled) setHardwareLabel(null); });
    }
    return () => { cancelled = true; };
  }, [real, realProvider]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        submit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-white/6 bg-[#0e0e13] lg:h-full lg:w-[380px] lg:border-r lg:border-b-0">
      <div className="flex items-center justify-between border-b border-white/6 px-4 py-3">
        <div className="flex items-center gap-2">
          <Clapperboard className="h-4 w-4 text-cyan-300" />
          <h2 className="text-sm font-medium text-zinc-100">新建视频</h2>
        </div>
        <span className="font-mono text-[10px] text-zinc-500">
          {busyCount > 0 ? `${busyCount} 个任务占用后端` : real ? `${model.shortName} · 受控实验` : "本机模拟服务"}
        </span>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <section>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[11px] font-medium tracking-wide text-zinc-400">首帧图片</label>
            {firstFrame && (
              <button
                onClick={() => setFirstFrame(undefined)}
                className="text-[11px] text-zinc-500 hover:text-zinc-300"
              >
                清除
              </button>
            )}
          </div>
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              onFile(e.dataTransfer.files[0]);
            }}
            className="group relative flex h-36 cursor-pointer items-center justify-center overflow-hidden rounded-xl border border-dashed border-white/10 bg-white/[0.02] transition hover:border-cyan-400/40"
          >
            {firstFrame ? (
              <>
                <img src={firstFrame} alt="首帧" className="h-full w-full object-cover" />
                <div className="absolute inset-0 bg-black/0 transition group-hover:bg-black/30" />
                <span className="absolute bottom-2 right-2 rounded-md bg-black/60 px-2 py-0.5 text-[10px] text-zinc-200 opacity-0 group-hover:opacity-100">
                  更换图片
                </span>
              </>
            ) : (
              <div className="flex flex-col items-center gap-1.5 text-zinc-500">
                <ImagePlus className="h-5 w-5" />
                <span className="text-[12px]">拖入或点击上传首帧</span>
                <span className="text-[10px] text-zinc-600">PNG / JPG · 用于图生视频</span>
              </div>
            )}
            <input
              ref={inputRef}
              type="file"
              accept="image/png,image/jpeg"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
          </div>
          <div className="mt-2 grid grid-cols-4 gap-1.5">
            {SAMPLE_FRAMES.map((f) => (
              <button
                key={f.url}
                onClick={() => setFirstFrame(f.url)}
                className={cn(
                  "relative overflow-hidden rounded-md ring-1 ring-white/8 transition",
                  firstFrame === f.url && "ring-2 ring-cyan-400",
                )}
                title={f.label}
              >
                <img src={f.url} alt={f.label} className="h-10 w-full object-cover" />
              </button>
            ))}
          </div>
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[11px] font-medium tracking-wide text-zinc-400">提示词</label>
            <span className="font-mono text-[10px] text-zinc-600">{prompt.length}</span>
          </div>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            placeholder="描述镜头、光线、运动与风格…"
            className="w-full resize-none rounded-xl border border-white/8 bg-[#14141b] px-3 py-2.5 text-[13px] leading-relaxed text-zinc-200 outline-none transition placeholder:text-zinc-600 focus:border-cyan-400/40"
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PROMPT_PRESETS.map((p, i) => (
              <button
                key={i}
                onClick={() => setPrompt(p)}
                className="rounded-full border border-white/8 bg-white/[0.03] px-2 py-0.5 text-[10px] text-zinc-400 hover:border-white/16 hover:text-zinc-200"
              >
                预设 {i + 1}
              </button>
            ))}
          </div>
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[11px] font-medium tracking-wide text-zinc-400">反向提示词</label>
            {negativePrompt && (
              <button onClick={() => setNegativePrompt("")} className="text-zinc-600 hover:text-zinc-300">
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
          <textarea
            value={negativePrompt}
            onChange={(e) => setNegativePrompt(e.target.value)}
            rows={2}
            placeholder="不希望出现的内容…"
            className="w-full resize-none rounded-xl border border-white/8 bg-[#14141b] px-3 py-2.5 text-[13px] text-zinc-200 outline-none transition placeholder:text-zinc-600 focus:border-cyan-400/40"
          />
        </section>

        <section>
          <label className="mb-2 block text-[11px] font-medium tracking-wide text-zinc-400">模型</label>
          <div className="space-y-1.5">
            {models.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  setModelId(m.id);
                  setDuration((d) => Math.min(d, m.maxDuration));
                }}
                className={cn(
                  "w-full rounded-xl border px-3 py-2.5 text-left transition",
                  model.id === m.id
                    ? "border-cyan-400/40 bg-cyan-400/8"
                    : "border-white/6 bg-white/[0.02] hover:border-white/12",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium text-zinc-100">{m.name}</span>
                      <span className="rounded bg-white/6 px-1.5 py-px font-mono text-[10px] text-zinc-500">
                        {m.backendLabel}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] leading-snug text-zinc-500">{m.description}</p>
                    {real && <p className="mt-1 text-[11px] leading-snug text-zinc-400" data-testid="real-model-hardware">
                      {hardwareLabel ?? "目标硬件：等待本机预检核验"}。生成显存峰值待测。
                    </p>}
                  </div>
                  <div className="shrink-0 text-right">
                    <ModelDot status={m.status} />
                    <div className="mt-1 font-mono text-[10px] text-zinc-500">
                      {real ? "费用按实例运行计费" : formatCost(m.costPerSecond) + "/s"}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>

        <section>
          <label className="mb-2 block text-[11px] font-medium tracking-wide text-zinc-400">画面比例</label>
          <div className="grid grid-cols-5 gap-1.5">
            {ASPECTS.filter(a=>!real || a.id === "9:16").map((a) => (
              <button
                key={a.id}
                onClick={() => setAspect(a.id)}
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-lg border px-1 py-2 transition",
                  aspect === a.id
                    ? "border-cyan-400/40 bg-cyan-400/8 text-cyan-100"
                    : "border-white/6 bg-white/[0.02] text-zinc-400 hover:border-white/12",
                )}
              >
                <span
                  className="rounded-[2px] bg-current/80"
                  style={{
                    width: Math.max(8, (a.w / Math.max(a.w, a.h)) * 18),
                    height: Math.max(8, (a.h / Math.max(a.w, a.h)) * 18),
                    opacity: 0.85,
                  }}
                />
                <span className="font-mono text-[10px]">{a.id}</span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <label className="mb-2 block text-[11px] font-medium tracking-wide text-zinc-400">
            时长 · 最长 {model.maxDuration}s
          </label>
          <div className="flex gap-1.5">
            {DURATIONS.filter((d) => real ? d === 5 : d <= model.maxDuration).map((d) => (
              <button
                key={d}
                onClick={() => setDuration(d)}
                className={cn(
                  "flex-1 rounded-lg border py-1.5 font-mono text-[12px] transition",
                  clampedDuration === d
                    ? "border-cyan-400/40 bg-cyan-400/8 text-cyan-100"
                    : "border-white/6 bg-white/[0.02] text-zinc-400 hover:border-white/12",
                )}
              >
                {d}s
              </button>
            ))}
          </div>
        </section>

        {!real && <section>
          <button
            onClick={() => setAdvanced((v) => !v)}
            className="flex w-full items-center justify-between text-[11px] text-zinc-500 hover:text-zinc-300"
          >
            高级参数
            <ChevronDown className={cn("h-3.5 w-3.5 transition", advanced && "rotate-180")} />
          </button>
          {advanced && (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field label="Seed">
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value))}
                  className="field-input"
                />
              </Field>
              <Field label="FPS">
                <select
                  value={fps}
                  onChange={(e) => setFps(Number(e.target.value))}
                  className="field-input"
                >
                  {[16, 24, 25, 30].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={`CFG ${cfg.toFixed(1)}`}>
                <input
                  type="range"
                  min={1}
                  max={12}
                  step={0.5}
                  value={cfg}
                  onChange={(e) => setCfg(Number(e.target.value))}
                />
              </Field>
              <Field label={`运动 ${motion.toFixed(2)}`}>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={motion}
                  onChange={(e) => setMotion(Number(e.target.value))}
                />
              </Field>
            </div>
          )}
        </section>}
      </div>

      <div className="border-t border-white/6 p-4">
        <p className="mb-2 text-[11px] text-amber-300">
          {real ? "真实实验仅限 5秒 / 9:16。资格未通过时禁止提交；生成后由 Bridge 自动下载到 Windows 并验证完整性。"
            : "仅本机 MOCK：须上传电脑里的PNG/JPG首帧；不会真正生成AI视频，也不会启动AWS。"}
        </p>
        <div className="mb-2 flex items-center justify-between text-[11px] text-zinc-500">
          <span>
            预计成本 <span className="font-mono text-zinc-200">{real ? "未测（按实例时长计费）" : formatCost(estimate)}</span>
          </span>
          <span className="font-mono">⌘↵</span>
        </div>
        <button
          onClick={submit}
          disabled={disabled || !prompt.trim() || !firstFrame?.startsWith("data:image/")}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-[#062824] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Sparkles className="h-4 w-4" />
          生成视频
        </button>
      </div>
    </aside>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-zinc-500">{label}</span>
      {children}
    </label>
  );
}
