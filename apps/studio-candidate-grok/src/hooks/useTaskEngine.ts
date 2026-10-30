import { useCallback, useEffect, useMemo, useState } from "react";
import { getModel, INITIAL_TASKS, pickClip } from "../data";
import type { CreatePayload, Task } from "../types";
import { uid } from "../utils/format";

const STORAGE_KEY = "aniflow.tasks.v1";

function loadTasks(): Task[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return INITIAL_TASKS;
    const extra = JSON.parse(raw) as Task[];
    const ids = new Set(INITIAL_TASKS.map((t) => t.id));
    return [...extra.filter((t) => !ids.has(t.id)), ...INITIAL_TASKS];
  } catch {
    return INITIAL_TASKS;
  }
}

function persist(tasks: Task[]) {
  const extras = tasks.filter((t) => !INITIAL_TASKS.some((s) => s.id === t.id));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(extras.slice(0, 40)));
}

export function useTaskEngine() {
  const [tasks, setTasks] = useState<Task[]>(loadTasks);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    persist(tasks);
  }, [tasks]);

  useEffect(() => {
    const id = window.setInterval(() => {
      setTick((n) => n + 1);
      setTasks((prev) =>
        prev.map((task) => {
          if (task.status === "queued") {
            const wait = Date.now() - task.createdAt;
            if (wait > 1600) {
              return {
                ...task,
                status: "running",
                startedAt: Date.now(),
                progress: 3,
                etaSeconds: Math.max(12, Math.round(task.duration * 8)),
              };
            }
            return task;
          }
          if (task.status !== "running") return task;
          const model = getModel(task.modelId);
          const speed = model?.backend === "minimax" ? 3.2 : model?.backend === "agnes" ? 4.4 : 2.4;
          const next = Math.min(100, task.progress + speed * (0.55 + Math.random() * 0.7));
          if (next >= 100) {
            const clip = pickClip();
            return {
              ...task,
              status: "done",
              progress: 100,
              etaSeconds: 0,
              finishedAt: Date.now(),
              videoUrl: clip.videoUrl,
              thumbnailUrl: clip.thumbnailUrl,
            };
          }
          const remain = Math.max(1, Math.round((100 - next) / speed));
          return { ...task, progress: next, etaSeconds: remain };
        }),
      );
    }, 420);
    return () => window.clearInterval(id);
  }, []);

  const createTask = useCallback((payload: CreatePayload) => {
    const model = getModel(payload.modelId);
    const cost = Number(((model?.costPerSecond ?? 0.01) * payload.duration).toFixed(3));
    const task: Task = {
      id: uid(),
      prompt: payload.prompt.trim(),
      negativePrompt: payload.negativePrompt.trim(),
      modelId: payload.modelId,
      aspectRatio: payload.aspectRatio,
      duration: payload.duration,
      fps: payload.fps,
      seed: payload.seed,
      cfg: payload.cfg,
      motion: payload.motion,
      status: "queued",
      progress: 0,
      etaSeconds: Math.round(payload.duration * 10),
      cost,
      createdAt: Date.now(),
      firstFrame: payload.firstFrame,
      thumbnailUrl: payload.firstFrame,
    };
    setTasks((prev) => [task, ...prev]);
    return task;
  }, []);

  const retryTask = useCallback((id: string) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id
          ? {
              ...t,
              status: "queued",
              progress: 0,
              etaSeconds: Math.round(t.duration * 10),
              error: undefined,
              createdAt: Date.now(),
              startedAt: undefined,
              finishedAt: undefined,
            }
          : t,
      ),
    );
  }, []);

  const removeTask = useCallback((id: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const stats = useMemo(() => {
    const queued = tasks.filter((t) => t.status === "queued").length;
    const running = tasks.filter((t) => t.status === "running").length;
    const done = tasks.filter((t) => t.status === "done").length;
    const failed = tasks.filter((t) => t.status === "failed").length;
    const todayCost = tasks
      .filter((t) => Date.now() - t.createdAt < 1000 * 60 * 60 * 18)
      .reduce((s, t) => s + (t.status === "failed" ? 0 : t.cost), 0);
    return { queued, running, done, failed, todayCost, total: tasks.length, tick };
  }, [tasks, tick]);

  return { tasks, createTask, retryTask, removeTask, stats };
}
