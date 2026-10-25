import { cn } from "../utils/cn";
import type { ModelStatus, TaskStatus } from "../types";

const taskMap: Record<TaskStatus, { label: string; className: string }> = {
  queued: {
    label: "等待",
    className: "bg-zinc-800 text-zinc-300 ring-zinc-700",
  },
  running: {
    label: "生成中",
    className: "bg-cyan-500/10 text-cyan-300 ring-cyan-500/30",
  },
  done: {
    label: "完成",
    className: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30",
  },
  failed: {
    label: "失败",
    className: "bg-rose-500/10 text-rose-300 ring-rose-500/30",
  },
};

const modelMap: Record<ModelStatus, { label: string; dot: string }> = {
  ready: { label: "就绪", dot: "bg-emerald-400" },
  busy: { label: "繁忙", dot: "bg-amber-400" },
  degraded: { label: "降级", dot: "bg-amber-400" },
  offline: { label: "离线", dot: "bg-rose-400" },
};

export function TaskBadge({ status }: { status: TaskStatus }) {
  const item = taskMap[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
        item.className,
      )}
    >
      {status === "running" && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-cyan-300" />}
      {status === "queued" && <span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />}
      {item.label}
    </span>
  );
}

export function ModelDot({ status }: { status: ModelStatus }) {
  const item = modelMap[status];
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          item.dot,
          status === "ready" ? "" : "pulse-dot",
        )}
      />
      {item.label}
    </span>
  );
}
