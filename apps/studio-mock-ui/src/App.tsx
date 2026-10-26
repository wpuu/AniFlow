import { useCallback, useEffect, useState } from "react";
import { CreatePanel } from "./components/CreatePanel";
import { AwsPreflightPanel } from "./components/AwsPreflightPanel";
import { Header } from "./components/Header";
import { PlayerModal } from "./components/PlayerModal";
import { TaskBoard } from "./components/TaskBoard";
import { useTaskEngine } from "./hooks/useTaskEngine";
import type { CreatePayload, StatusFilter, StudioMode, Task } from "./types";

export default function App() {
  const [mode, setMode] = useState<StudioMode>("mock");
  return <Workspace key={mode} mode={mode} onMode={setMode} />;
}

function Workspace({mode, onMode}: {mode:StudioMode; onMode:(mode:StudioMode)=>void}) {
  const { tasks, createTask, retryTask, removeTask, stats, error, pending, recoverPending, forgetPending, service } = useTaskEngine(mode);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [active, setActive] = useState<Task | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [showAwsPreflight, setShowAwsPreflight] = useState(false);
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
        flash((mode === "real" ? "已提交真实 H3 请求：" : "已提交本机 MOCK 任务：") + task.id);
        setFilter("all");
      } catch (err) {
        flash("提交未确认，请核查原任务：" + (err instanceof Error ? err.message : String(err)));
      }
    },
    [createTask, flash, mode],
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
      <div data-testid={mode === "mock" ? "strict-mock-banner" : "strict-real-banner"}
        className="border-b border-amber-600/40 bg-amber-950/60 px-4 py-2 text-center text-xs font-semibold text-amber-200">
        {mode === "mock"
          ? "本机模拟模式 · 未连接 AWS / ComfyUI / Agnes · 费用 $0 · 结果仅为蓝色测试 MP4"
          : "真实 H3 模式 · 仅通过本机 SSM 隧道 · MP4 自动保存并校验后才算完成 · 费用以实际账单为准"}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 bg-[#0c0c10] px-4 py-1.5">
        <div className="flex gap-2" aria-label="工作模式">
          {(["mock", "real"] as const).map(value => <button key={value} type="button"
            aria-pressed={mode === value} onClick={() => onMode(value)}
            className="rounded-lg border border-white/20 px-3 py-1.5 text-xs aria-pressed:border-cyan-400 aria-pressed:text-cyan-200">
            {value === "mock" ? "本机 Mock" : "真实 H3"}
          </button>)}
        </div>
        <button type="button" data-testid="open-aws-preflight"
          onClick={() => setShowAwsPreflight(true)}
          className="rounded-lg border border-cyan-400/25 px-3 py-1.5 text-[11px] font-medium text-cyan-200 hover:bg-cyan-400/10">
          AWS 东京 H3：部署前资格核验
        </button>
      </div>
      {(!service.ready || service.mode !== mode) && <div role="status" data-testid="mode-blocked"
        className="border-b border-amber-500/30 bg-amber-950/50 px-4 py-3 text-xs text-amber-200">
        {service.mode && service.mode !== mode
          ? `当前服务仅支持${service.mode === "real" ? "真实 H3" : "Mock"}；请打开本机 ${mode === "real" ? "8768" : "8767"} 对应服务，再显式选择此模式。`
          : mode === "real" ? "真实生成已禁用：等待资格、配额、许可与双重停机保护核验通过。" : "正在核查本机 Mock 服务，未确认前禁止提交。"}
        {service.reasons.length > 0 && <ul className="mt-2 list-disc pl-4">{service.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}
      </div>}
      {pending && (
        <div data-testid="pending-unknown-create"
          className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-500/30 bg-amber-950/75 px-4 py-3 text-xs text-amber-100">
          <span>上次任务提交结果未知，已保存原请求编号。为避免未来 GPU 重复扣费，已暂停新的提交。</span>
          <div className="flex gap-2">
            <button type="button" onClick={() => {
              void recoverPending()
                .then(task => flash(task ? "已找回原任务：" + task.id : "原任务尚未查到；继续保留保护"))
                .catch(err => flash("核查未完成：" + String(err)));
            }} className="rounded border border-amber-300/50 px-2 py-1">查询原任务</button>
            <button type="button" onClick={() => {
              if (window.confirm("无法查到不代表没有提交成功。放弃保护可能导致未来重复生成或扣费。确定仅清除本地保护？")) {
                try { forgetPending(); flash("仅清除了本地保护，云端原任务没有被取消"); }
                catch (err) { flash("操作失败：" + String(err)); }
              }
            }} className="rounded border border-amber-300/30 px-2 py-1 text-amber-200">确认放弃保护</button>
          </div>
        </div>
      )}
      {error && <div role="alert" className="bg-rose-950/80 px-4 py-2 text-xs text-rose-200">本机 Bridge 提示：{error}</div>}
      <Header
        queued={stats.queued}
        running={stats.running}
        todayCost={stats.todayCost}
        clock={clock}
        mode={mode}
        ready={service.ready}
        tunnelConnected={service.tunnelConnected}
        gpuConnected={service.gpuConnected}
      />

      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <CreatePanel onSubmit={handleCreate} busyCount={stats.queued + stats.running}
          mode={mode} disabled={Boolean(pending) || !service.ready || service.mode !== mode} />
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
          }}
        />
      </main>

      {showAwsPreflight && (
        <AwsPreflightPanel mode={mode} onClose={() => setShowAwsPreflight(false)} />
      )}

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
