import { useCallback, useEffect, useState } from "react";
import { CreatePanel } from "./components/CreatePanel";
import { Header } from "./components/Header";
import { PlayerModal } from "./components/PlayerModal";
import { TaskBoard } from "./components/TaskBoard";
import { useTaskEngine } from "./hooks/useTaskEngine";
import type { CreatePayload, StatusFilter, Task } from "./types";

export default function App() {
  const { tasks, createTask, retryTask, removeTask, stats, error } = useTaskEngine();
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
    async (payload: CreatePayload) => {
      try {
        const task = await createTask(payload);
        flash("已提交本机 MOCK 任务：" + task.id);
        setFilter("all");
      } catch (err) {
        flash("没有创建任务：" + (err instanceof Error ? err.message : String(err)));
      }
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
      <div data-testid="strict-mock-banner"
        className="border-b border-amber-600/40 bg-amber-950/60 px-4 py-2 text-center text-xs font-semibold text-amber-200">
        本机模拟模式 · 未连接 AWS / ComfyUI / Agnes · 费用 $0 · 结果仅为蓝色测试 MP4
      </div>
      {error && <div className="bg-rose-950/80 px-4 py-2 text-xs text-rose-200">Mock Bridge连接失败：{error}</div>}
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
            try { retryTask(id); }
            catch (err) { flash(err instanceof Error ? err.message : "Mock 重试禁用"); }
          }}
          onRemove={(id) => {
            removeTask(id);
            if (active?.id === id) setActive(null);
            flash("已从本机列表隐藏；SQLite原任务和文件均未删除");
          }
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
