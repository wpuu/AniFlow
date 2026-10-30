import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Check,
  Copy,
  Download,
  Maximize,
  Pause,
  Play,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { getModel } from "../data";
import type { Task } from "../types";
import { formatCost, formatDate } from "../utils/format";

interface PlayerModalProps {
  task: Task;
  onClose: () => void;
  onDownload: () => void;
}

export function PlayerModal({ task, onClose, onDownload }: PlayerModalProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [progress, setProgress] = useState(0);
  const [copied, setCopied] = useState(false);
  const model = getModel(task.modelId);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === " " && videoRef.current) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function toggle() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      void v.play();
      setPlaying(true);
    } else {
      v.pause();
      setPlaying(false);
    }
  }

  async function copyPrompt() {
    await navigator.clipboard.writeText(task.prompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-6xl overflow-hidden rounded-2xl border border-white/8 bg-[#101016] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex min-w-0 flex-1 flex-col bg-black">
          <div className="relative flex-1 bg-black">
            {task.videoUrl ? (
              <video
                ref={videoRef}
                src={task.videoUrl}
                poster={task.thumbnailUrl}
                className="h-full max-h-[72vh] w-full object-contain"
                onTimeUpdate={(e) => {
                  const v = e.currentTarget;
                  setProgress(v.duration ? (v.currentTime / v.duration) * 100 : 0);
                }}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onClick={toggle}
                autoPlay
                playsInline
              />
            ) : (
              <div className="flex h-[52vh] items-center justify-center text-sm text-zinc-500">
                视频尚未就绪
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 border-t border-white/8 bg-[#0c0c10] px-4 py-3">
            <button onClick={toggle} className="text-zinc-200 hover:text-white">
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
            </button>
            <div
              className="h-1.5 flex-1 cursor-pointer overflow-hidden rounded-full bg-white/10"
              onClick={(e) => {
                const v = videoRef.current;
                if (!v || !v.duration) return;
                const rect = e.currentTarget.getBoundingClientRect();
                v.currentTime = ((e.clientX - rect.left) / rect.width) * v.duration;
              }}
            >
              <div className="h-full bg-cyan-400" style={{ width: `${progress}%` }} />
            </div>
            <button onClick={() => {
              const v = videoRef.current;
              if (!v) return;
              v.muted = !v.muted;
              setMuted(v.muted);
            }} className="text-zinc-400 hover:text-white">
              {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>
            <button
              onClick={() => videoRef.current?.requestFullscreen()}
              className="text-zinc-400 hover:text-white"
            >
              <Maximize className="h-4 w-4" />
            </button>
            <button
              onClick={onDownload}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white/8 px-2.5 py-1 text-[12px] text-zinc-200 hover:bg-white/12"
            >
              <Download className="h-3.5 w-3.5" />
              下载
            </button>
          </div>
        </div>

        <aside className="flex w-[320px] shrink-0 flex-col border-l border-white/8">
          <div className="flex items-center justify-between border-b border-white/8 px-4 py-3">
            <div>
              <div className="font-mono text-[11px] text-zinc-500">{task.id}</div>
              <div className="text-sm text-zinc-100">生成参数</div>
            </div>
            <button onClick={onClose} className="rounded-md p-1 text-zinc-500 hover:bg-white/8 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-[12px]">
            <Param label="提示词">
              <p className="leading-relaxed text-zinc-300">{task.prompt}</p>
              <button
                onClick={copyPrompt}
                className="mt-2 inline-flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200"
              >
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                {copied ? "已复制" : "复制提示词"}
              </button>
            </Param>
            <Param label="反向提示词">
              <p className="text-zinc-400">{task.negativePrompt || "—"}</p>
            </Param>
            {task.firstFrame && (
              <Param label="首帧">
                <img src={task.firstFrame} alt="" className="mt-1 h-20 w-full rounded-lg object-cover" />
              </Param>
            )}
            <div className="grid grid-cols-2 gap-2">
              <KV k="模型" v={model?.name ?? task.modelId} />
              <KV k="后端" v={model?.backendLabel ?? "—"} />
              <KV k="比例" v={task.aspectRatio} />
              <KV k="时长" v={`${task.duration}s`} />
              <KV k="FPS" v={String(task.fps)} />
              <KV k="Seed" v={String(task.seed)} />
              <KV k="CFG" v={task.cfg.toFixed(1)} />
              <KV k="运动" v={task.motion.toFixed(2)} />
              <KV k="成本" v={formatCost(task.cost)} />
              <KV k="创建" v={formatDate(task.createdAt)} />
            </div>
            {task.error && (
              <Param label="错误">
                <p className="text-rose-300">{task.error}</p>
              </Param>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function Param({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      {children}
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-lg border border-white/6 bg-white/[0.03] px-2.5 py-2">
      <div className="text-[10px] text-zinc-500">{k}</div>
      <div className="mt-0.5 font-mono text-[11px] text-zinc-200">{v}</div>
    </div>
  );
}
