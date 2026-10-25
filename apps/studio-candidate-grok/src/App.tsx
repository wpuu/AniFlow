import { useCallback, useEffect, useState } from "react";
import { CreatePanel } from "./components/CreatePanel";
import { Header } from "./components/Header";
import { PlayerModal } from "./components/PlayerModal";
import { TaskBoard } from "./components/TaskBoard";
import { useTaskEngine } from "./hooks/useTaskEngine";
import type { CreatePayload, StatusFilter, Task } from "./types";

export default function App() {
  const { tasks, createTask, retryTask, removeTask, stats } = useTaskEngine();
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [active, setActive] = useState<Task | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [clock, setClock] = useState(Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(id);
  }, [toast]);

  const flash = useCallback((msg: string) => setToast(msg), []);

  const handleCreate = useCallback(
    (payload: CreatePayload) => {
      const task = createTask(payload);
      flash(`已提交 ${task.id} → 队列`);
      setFilter("all");
    },
    [createTask, flash],
  );

  async function handleDownload(task: Task) {
    if (!task.videoUrl) {
      flash("视频尚未就绪");
      return;
    }
    try {
      const res = await fetch(task.videoUrl);
      if (!res.ok) throw new Error("network");
      const blob = await res.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `${task.id}.mp4`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
      flash(`开始下载 ${task.id}.mp4`);
    } catch {
      window.open(task.videoUrl, "_blank");
      flash("已在新标签打开视频");
    }
  }

  const liveActive = active ? (tasks.find((t) => t.id === active.id) ?? active) : null;

  return (
    <div className="noise flex h-full min-h-0 flex-col bg-[#08080a] text-zinc-200">
      <Header
        queued={stats.queued}
        running={stats.running}
        todayCost={stats.todayCost}
        clock={clock}
      />

      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <CreatePanel onSubmit={handleCreate} busyCount={stats.queued + stats.running} />
        <TaskBoard
          tasks={tasks}
          filter={filter}
          onFilter={setFilter}
          selectedId={active?.id}
          onPlay={(t) => setActive(t)}
          onParams={(t) => setActive(t)}
          onDownload={(t) => void handleDownload(t)}
          onRetry={(id) => {
            retryTask(id);
            flash(`${id} 已重新入队`);
          }}
          onRemove={(id) => {
            removeTask(id);
            if (active?.id === id) setActive(null);
          }}
        />
      </main>

      {liveActive && (
        <PlayerModal
          task={liveActive}
          onClose={() => setActive(null)}
          onDownload={() => void handleDownload(liveActive)}
        />
      )}

      {toast && (
        <div className="pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full border border-white/10 bg-[#16161c]/95 px-4 py-2 font-mono text-[12px] text-zinc-100 shadow-xl backdrop-blur">
          {toast}
        </div>
      )}
    </div>
  );
}
