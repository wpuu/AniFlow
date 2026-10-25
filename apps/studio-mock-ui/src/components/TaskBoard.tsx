import { Film, Inbox } from "lucide-react";
import type { StatusFilter, Task } from "../types";
import { cn } from "../utils/cn";
import { TaskCard } from "./TaskCard";

interface TaskBoardProps {
  tasks: Task[];
  filter: StatusFilter;
  onFilter: (f: StatusFilter) => void;
  selectedId?: string;
  onPlay: (t: Task) => void;
  onParams: (t: Task) => void;
  onDownload: (t: Task) => void;
  onRetry: (id: string) => void;
  onRemove: (id: string) => void;
}

const FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "queued", label: "等待" },
  { id: "running", label: "生成中" },
  { id: "downloading", label: "下载校验" },
  { id: "submission_unknown", label: "待确认" },
  { id: "done", label: "完成" },
  { id: "failed", label: "失败" },
];

export function TaskBoard({
  tasks,
  filter,
  onFilter,
  selectedId,
  onPlay,
  onParams,
  onDownload,
  onRetry,
  onRemove,
}: TaskBoardProps) {
  const counts: Record<StatusFilter, number> = {
    all: tasks.length,
    queued: tasks.filter((t) => t.status === "queued").length,
    running: tasks.filter((t) => t.status === "running").length,
    downloading: tasks.filter((t) => t.status === "downloading").length,
    submission_unknown: tasks.filter((t) => t.status === "submission_unknown").length,
    done: tasks.filter((t) => t.status === "done").length,
    failed: tasks.filter((t) => t.status === "failed").length,
  };

  const visible = filter === "all" ? tasks : tasks.filter((t) => t.status === filter);

  return (
    <section className="flex min-h-[560px] min-w-0 flex-1 flex-col bg-[#0a0a0e] lg:min-h-0">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/6 px-5 py-3">
        <div className="flex items-center gap-2">
          <Film className="h-4 w-4 text-zinc-400" />
          <h2 className="text-sm font-medium text-zinc-100">任务队列</h2>
          <span className="font-mono text-[11px] text-zinc-500">{visible.length}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1 rounded-lg bg-white/[0.03] p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => onFilter(f.id)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11px] transition",
                filter === f.id ? "bg-white/10 text-zinc-100" : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              {f.label}
              <span className="ml-1 font-mono text-[10px] text-zinc-500">{counts[f.id]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {visible.length === 0 ? (
          <div className="flex h-full min-h-[240px] flex-col items-center justify-center text-zinc-600">
            <Inbox className="mb-2 h-8 w-8" />
            <p className="text-sm">没有符合条件的任务</p>
          </div>
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {visible.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                selected={selectedId === task.id}
                onPlay={() => onPlay(task)}
                onParams={() => onParams(task)}
                onDownload={() => onDownload(task)}
                onRetry={() => onRetry(task.id)}
                onRemove={() => onRemove(task.id)}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
