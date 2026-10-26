import { Activity, Cpu } from "lucide-react";
import { MODELS, REAL_MODEL } from "../data";
import type { Model, StudioMode } from "../types";
import { formatClock, formatCost } from "../utils/format";
import { ModelDot } from "./StatusBadge";

interface HeaderProps {
  queued: number;
  running: number;
  todayCost: number | null;
  clock: number;
  mode: StudioMode;
  ready: boolean;
  tunnelConnected: boolean;
  gpuConnected: boolean;
}

function BackendPill({ model }: { model: Model }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-white/6 bg-white/[0.03] px-2.5 py-1">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          model.status === "ready"
            ? "bg-emerald-400"
            : model.status === "offline"
              ? "bg-rose-400"
              : "bg-amber-400 pulse-dot"
        }`}
      />
      <span className="text-[11px] font-medium tracking-wide text-zinc-200">{model.backendLabel}</span>
      <span className="font-mono text-[10px] text-zinc-500">{model.id === "mock-h3" ? "仅 Mock" : "真实模式"}</span>
    </div>
  );
}

export function Header({ queued, running, todayCost, clock, mode, ready, tunnelConnected, gpuConnected }: HeaderProps) {
  const models: Model[] = mode === "real" ? [{...REAL_MODEL, status:ready ? "ready" : "offline"}] : MODELS;
  const uniqueBackends = models.filter(
    (m, i, arr) => arr.findIndex((x) => x.backend === m.backend) === i,
  ).map((base) => {
    const group = models.filter((m) => m.backend === base.backend);
    const worst =
      group.find((m) => m.status === "offline") ??
      group.find((m) => m.status === "degraded") ??
      group.find((m) => m.status === "busy") ??
      base;
    return {
      ...base,
      status: worst.status,
      latencyMs: Math.max(...group.map((g) => g.latencyMs)),
    };
  });

  return (
    <header className="relative z-20 flex h-14 shrink-0 items-center justify-between border-b border-white/6 bg-[#0c0c10]/90 px-4 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <img src="/images/logo.png" alt="AniFlow" className="h-8 w-8 rounded-lg ring-1 ring-white/10" />
        <div className="leading-tight">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[17px] font-bold tracking-tight text-white">AniFlow</span>
            <span className="text-[11px] text-zinc-500">个人视频工作台</span>
          </div>
        </div>
        <div className="ml-4 hidden items-center gap-2 rounded-full border border-white/6 bg-white/[0.03] px-3 py-1 lg:flex">
          <Activity className="h-3.5 w-3.5 text-cyan-300" />
          <span className="text-[11px] text-zinc-300">{mode === "mock" ? "本机模拟 · 无真实GPU"
            : !tunnelConnected ? "真实 H3 · 私有连接未确认连通"
            : gpuConnected ? "私有连接连通 · CUDA设备已观察（H3显存峰值仍待测）"
            : "私有连接连通 · 尚未观察到CUDA设备"}</span>
          <span className="text-zinc-700">·</span>
          <span className="font-mono text-[11px] text-zinc-500">{formatClock(clock)}</span>
        </div>
      </div>

      <div className="hidden items-center gap-1.5 md:flex">
        {uniqueBackends.map((m) => (
          <BackendPill key={m.backend} model={m} />
        ))}
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-2 rounded-lg border border-white/6 bg-white/[0.03] px-2.5 py-1 sm:flex">
          <Cpu className="h-3.5 w-3.5 text-zinc-500" />
          <span className="text-[11px] text-zinc-400">
            队列 <span className="font-mono text-zinc-200">{queued}</span>
          </span>
          <span className="text-zinc-700">/</span>
          <span className="text-[11px] text-zinc-400">
            生成 <span className="font-mono text-cyan-300">{running}</span>
          </span>
        </div>
        <div className="rounded-lg border border-white/6 bg-white/[0.03] px-2.5 py-1">
          <span className="text-[11px] text-zinc-500">今日成本 </span>
          <span className="font-mono text-[11px] text-zinc-200">{formatCost(todayCost)}</span>
        </div>
        <div className="hidden xl:block">
          <ActiveModel model={models[0]} />
        </div>
      </div>
    </header>
  );
}

function ActiveModel({model:current}: {model:Model}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-cyan-500/20 bg-cyan-400/5 px-2.5 py-1">
      <span className="text-[11px] text-zinc-400">{current.id === "mock-h3" ? "模拟模型" : "真实模型"}</span>
      <span className="text-[11px] font-medium text-cyan-200">{current.name}</span>
      <ModelDot status={current.status} />
    </div>
  );
}
