import type { ReactNode } from "react";
import {
  AlertTriangle,
  Clock3,
  Download,
  Play,
  RotateCcw,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { getModel } from "../data";
import type { Task } from "../types";
import { cn } from "../utils/cn";
import { formatCost, formatEta, relativeTime } from "../utils/format";
import { TaskBadge } from "./StatusBadge";

interface TaskCardProps {
  task: Task;
  selected: boolean;
  onPlay: () => void;
  onParams: () => void;
  onDownload: () => void;
  onRetry: () => void;
  onRemove: () => void;
}

export function TaskCard({
  task,
  selected,
  onPlay,
  onParams,
  onDownload,
  onRetry,
  onRemove,
}: TaskCardProps) {
  const model = getModel(task.modelId);

  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-2xl border bg-[#121218] transition",
        selected ? "border-cyan-400/40 ring-1 ring-cyan-400/20" : "border-white/6 hover:border-white/12",
      )}
    >
      <div className="flex gap-0">
        <div className="relative h-[132px] w-[196px] shrink-0 overflow-hidden bg-black">
          {task.thumbnailUrl || task.firstFrame ? (
            <img
              src={task.thumbnailUrl || task.firstFrame}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="grid-bg h-full w-full" />
          )}
          {task.status === "running" && (
            <div className="absolute inset-0 overflow-hidden bg-cyan-950/30">
              <div className="scan-line absolute left-0 h-1/2 w-full bg-gradient-to-b from-transparent via-cyan-300/25 to-transparent" />
            </div>
          )}
          {task.status === "done" && (
            <button
              onClick={onPlay}
              className="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 transition group-hover:opacity-100"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 text-zinc-900 shadow-lg">
                <Play className="ml-0.5 h-4 w-4 fill-current" />
              </span>
            </button>
          )}
          {task.status === "failed" && (
            <div className="absolute inset-0 flex items-center justify-center bg-rose-950/50">
              <AlertTriangle className="h-5 w-5 text-rose-300" />
            </div>
          )}
          <div className="absolute left-2 top-2">
            <TaskBadge status={task.status} />
          </div>
          <div className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-zinc-200">
            {task.aspectRatio} · {task.duration}s
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-zinc-500">{task.id}</span>
                <span className="truncate text-[11px] text-zinc-500">{model?.backendLabel}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-zinc-200">{task.prompt}</p>
            </div>
            <span className="shrink-0 font-mono text-[11px] text-zinc-400">{formatCost(task.cost)}</span>
          </div>

          {task.status === "running" && (
            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between font-mono text-[10px] text-zinc-500">
                <span>{Math.round(task.progress)}%</span>
                <span className="inline-flex items-center gap-1">
                  <Clock3 className="h-3 w-3" />
                  预计 {formatEta(task.etaSeconds)}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/8">
                <div
                  className="barber-progress h-full rounded-full bg-cyan-400/80"
                  style={{ width: `${task.progress}%` }}
                />
              </div>
            </div>
          )}

          {task.status === "queued" && (
            <p className="mt-3 text-[11px] text-zinc-500">排队中 · 预计等待 {formatEta(task.etaSeconds)}</p>
          )}

          {task.status === "failed" && (
            <p className="mt-2 line-clamp-2 text-[11px] text-rose-300/90">{task.error}</p>
          )}

          <div className="mt-auto flex items-center justify-between pt-3">
            <span className="text-[10px] text-zinc-600">{relativeTime(task.createdAt)}</span>
            <div className="flex items-center gap-1">
              {task.status === "done" && (
                <>
                  <IconBtn title="播放" onClick={onPlay}>
                    <Play className="h-3.5 w-3.5" />
                  </IconBtn>
                  <IconBtn title="下载" onClick={onDownload}>
                    <Download className="h-3.5 w-3.5" />
                  </IconBtn>
                </>
              )}
              {task.status === "failed" && (
                <IconBtn title="重试" onClick={onRetry}>
                  <RotateCcw className="h-3.5 w-3.5" />
                </IconBtn>
              )}
              <IconBtn title="生成参数" onClick={onParams}>
                <SlidersHorizontal className="h-3.5 w-3.5" />
              </IconBtn>
              <IconBtn title="仅隐藏列表（不会删除本地任务或视频）" onClick={onRemove}>
                <Trash2 className="h-3.5 w-3.5" />
              </IconBtn>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

function IconBtn({
  children,
  onClick,
  title,
}: {
  children: ReactNode;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/6 hover:text-zinc-200"
    >
      {children}
    </button>
  );
}
