import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CreatePayload, StudioMode, Task } from "../types";

interface ServerJob {
  id: string; project_id: string; shot_id: string; image_id: string;
  prompt: string; negative_prompt: string; aspect_ratio: Task["aspectRatio"];
  duration_seconds: number; provider: string; created_at: number;
  status: "queued" | "running" | "submission_unknown" | "downloading" | "completed" | "failed";
  progress: number | null; video_download_path: string | null;
  actual_cost_usd: number | null; simulation: boolean; gpu_connected: boolean;
  comfy_prompt_id?: string; local_path?: string; output_sha256?: string;
  output_bytes?: number; video_metadata?: Task["videoMetadata"]; verified?: boolean;
  elapsed_seconds?: number | null; peak_vram_mb?: number | null; error?: string;
}

export interface ServiceHealth {
  mode: StudioMode | null;
  ready: boolean;
  connected: boolean;
  reasons: string[];
}

export interface PendingSubmission {
  key: string;
  createdAt: number;
}

function readPending(storageKey: string): PendingSubmission | null {
  try {
    const obj: unknown = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (obj && typeof obj === "object" && "key" in obj && "createdAt" in obj) {
      const key = (obj as {key:unknown}).key;
      const createdAt = (obj as {createdAt:unknown}).createdAt;
      if (typeof key === "string" && /^[A-Za-z0-9_-]{8,128}$/.test(key)
          && typeof createdAt === "number" && Number.isFinite(createdAt)) {
        return {key, createdAt};
      }
    }
  } catch { /* no cross-origin or external access; uncertain state stays blocked */ }
  return null;
}
export function toTask(job: ServerJob, mode: StudioMode): Task {
  const api = "/api/studio/" + mode;
  const real = mode === "real";
  if (real ? job.simulation !== false || job.provider !== "minimax-h3"
    : job.simulation !== true || job.gpu_connected !== false || job.provider !== "mock-h3") {
    throw new Error("任务来源与当前模式不符，已拒绝混入历史");
  }
  const metadata = job.video_metadata;
  const verified = job.verified === true && Boolean(job.local_path)
    && /^[a-f0-9]{64}$/i.test(job.output_sha256 ?? "") && (job.output_bytes ?? 0) > 0
    && Boolean(metadata && [metadata.width, metadata.height, metadata.duration_seconds, metadata.fps]
      .every(value => typeof value === "number" && Number.isFinite(value) && value > 0));
  if (!["queued", "running", "submission_unknown", "downloading", "completed", "failed"].includes(job.status)) {
    throw new Error("服务器返回未知任务状态");
  }
  if (real && job.status === "completed" && !verified) {
    throw new Error("真实视频尚未通过本机文件、SHA256与MP4元数据验证，不能显示完成");
  }
  if (job.video_download_path && !job.video_download_path.startsWith(api + "/jobs/")) {
    throw new Error("视频地址不属于当前本机服务");
  }
  return {
    id: job.id, prompt: job.prompt, negativePrompt: job.negative_prompt,
    modelId: real ? "minimax-h3" : "mock-h3", aspectRatio: job.aspect_ratio,
    duration: job.duration_seconds, fps: 24, seed: 0, cfg: 0, motion: 0,
    status: job.status === "completed" ? "done" : job.status,
    progress: job.progress, etaSeconds: real ? null : Math.max(0, Math.ceil(6 - (Date.now()/1000 - job.created_at))),
    cost: real ? job.actual_cost_usd ?? null : 0, createdAt: job.created_at*1000,
    firstFrame: api + "/assets/" + job.image_id,
    thumbnailUrl: api + "/assets/" + job.image_id,
    videoUrl: job.status === "completed" ? job.video_download_path ?? undefined : undefined,
    promptId: job.comfy_prompt_id, localPath: job.local_path, sha256: job.output_sha256,
    outputBytes: job.output_bytes, verified: real ? verified : undefined,
    videoMetadata: metadata, elapsedSeconds: job.elapsed_seconds,
    peakVramMb: job.peak_vram_mb, error: job.error,
  };
}
async function jsonOrError(res: Response): Promise<any> {
  let body: any;
  try { body = await res.json(); } catch { throw new Error("本机 Bridge 返回无法解析的响应"); }
  if (!res.ok) throw new Error(typeof body?.detail === "string" ? body.detail : "HTTP " + res.status);
  return body;
}
export function useTaskEngine(mode: StudioMode) {
  const API = "/api/studio/" + mode;
  const HIDDEN_KEY = "aniflow." + mode + ".hidden_ids.v1";
  const PENDING_KEY = "aniflow." + mode + ".pending_submission.v1";
  const [service, setService] = useState<ServiceHealth>({mode:null, ready:false, connected:false, reasons:[]});
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(HIDDEN_KEY) || "[]");
      return new Set(Array.isArray(v) ? v.filter((i)=>typeof i==="string") : []);
    } catch { return new Set(); }
  });
  const [pending, setPending] = useState<PendingSubmission | null>(() => readPending(PENDING_KEY));
  const pendingRef = useRef<PendingSubmission | null>(pending);
  const [error, setError] = useState<string|null>(null);
  const submitting = useRef(false);

  const persistPending = useCallback((next: PendingSubmission | null) => {
    // Persist the idempotency key before sending any create POST.
    // No prompt, image, account or AWS credentials are stored here.
    if (next) localStorage.setItem(PENDING_KEY, JSON.stringify(next));
    else localStorage.removeItem(PENDING_KEY);
    pendingRef.current = next;
    setPending(next);
  }, [PENDING_KEY]);

  const checkService = useCallback(async () => {
    const realResponse = await fetch("/api/studio/real/health", {cache:"no-store"});
    let next: ServiceHealth;
    if (realResponse.status === 404) {
      const mock = await jsonOrError(await fetch("/api/studio/mock/health", {cache:"no-store"}));
      if (mock.mode !== "MOCK_ONLY" || mock.provider !== "mock-h3") throw new Error("未知本机服务");
      next = {mode:"mock", ready:mode === "mock", connected:false, reasons:[]};
    } else {
      const real = await jsonOrError(realResponse);
      if (real.mode !== "REAL_H3" || real.simulation !== false || real.provider !== "minimax-h3") {
        throw new Error("真实服务身份不符");
      }
      next = {mode:"real", ready:mode === "real" && real.ready === true,
        connected:real.gpu_connected === true, reasons:Array.isArray(real.blocked_reasons) ? real.blocked_reasons : []};
    }
    setService(next);
    return next;
  }, [mode]);

  const refresh = useCallback(async () => {
    const health = await checkService();
    if (health.mode !== mode) {
      setAllTasks([]);
      return;
    }
    const response = await fetch(API + "/jobs?limit=100", {cache: "no-store"});
    const body = await jsonOrError(response);
    if (body.simulation !== (mode === "mock") || !Array.isArray(body.jobs)) {
      throw new Error("服务器不是预期模式的本机 Bridge");
    }
    setAllTasks(body.jobs.map((job:ServerJob) => toTask(job, mode)));
    setError(null);
  }, [API, mode, checkService]);

  const recoverPending = useCallback(async (): Promise<Task | null> => {
    const attempt = pendingRef.current;
    if (!attempt) return null;
    const response = await fetch(API + "/requests/" + encodeURIComponent(attempt.key), {
      cache: "no-store",
    });
    if (response.status === 404) {
      setError("原提交尚未查到；保留请求保护，不会自动再次创建。可稍后重查。");
      return null;
    }
    const accepted = toTask(await jsonOrError(response), mode);
    // Keep the guard if local history synchronization fails.
    await refresh();
    persistPending(null);
    setAllTasks(prev => [accepted, ...prev.filter(t=>t.id!==accepted.id)]);
    setError(null);
    return accepted;
  }, [API, mode, refresh, persistPending]);

  useEffect(() => {
    const failed = (e:unknown) => { setError(String(e)); setService(prev=>({...prev, ready:false})); };
    void refresh().catch(failed);
    if (pendingRef.current) {
      void recoverPending().catch(e=>setError(
        "未知提交暂未核实：" + String(e) + "。不会再次提交。"));
    }
    const id=window.setInterval(()=>{void refresh().catch(failed);},1600);
    return ()=>window.clearInterval(id);
  },[refresh, recoverPending]);

  const createTask = useCallback(async(payload:CreatePayload):Promise<Task>=>{
    if (submitting.current) throw new Error("上次提交仍在进行，未创建重复任务");
    if (pendingRef.current) {
      throw new Error("上次创建请求结果未确认，请先点击「查询原任务」；禁止再次创建以避免重复扣费");
    }
    if (!payload.firstFrame?.startsWith("data:image/")) {
      throw new Error("请先上传电脑中的 PNG/JPG 首帧，示例网络图片不能提交");
    }
    submitting.current = true;
    try {
      const health = await checkService();
      if (!health.ready || health.mode !== mode) throw new Error("当前服务不支持此模式或真实预检未通过，已阻止提交");
      const blob = await fetch(payload.firstFrame).then(r=>r.blob());
      if (blob.size > 10*1024*1024) throw new Error("首帧超过10MB");
      const filename = blob.type === "image/png" ? "frame.png" : "frame.jpg";
      const form = new FormData();
      form.append("file",blob,filename);
      const asset=await jsonOrError(await fetch(API + "/assets", {method:"POST",body:form}));
      const key = typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : "mock-" + Date.now() + "-" + Math.random().toString(36).slice(2);
      // Guard is durable before the potentially chargeable operation.
      persistPending({key, createdAt:Date.now()});
      const response = await fetch(API + "/jobs",{
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          project_id:"SnowDirector", shot_id:"MYCL001-01",
          image_id:asset.image_id, prompt:payload.prompt,
          negative_prompt:payload.negativePrompt,
          duration_seconds:payload.duration, aspect_ratio:payload.aspectRatio,
          idempotency_key:key, provider:mode === "real" ? "minimax-h3" : "mock-h3",
        }),
      });
      if (!response.ok && [400, 401, 403, 404, 422].includes(response.status)) {
        // Explicit server rejection means no job accepted under this key.
        persistPending(null);
      }
      const result:ServerJob = await jsonOrError(response);
      const created=toTask(result, mode);
      persistPending(null);
      setAllTasks(prev=>[created,...prev.filter(t=>t.id!==created.id)]);
      return created;
    } finally {
      submitting.current = false;
    }
  },[API, mode, checkService, persistPending]);

  const forgetPending = useCallback(() => {
    // Explicit owner acknowledgement only. May leave an accepted remote job.
    if (submitting.current) throw new Error("提交请求仍在发送，不允许放弃保护");
    persistPending(null);
    setError(null);
  }, [persistPending]);

  const removeTask=useCallback((id:string)=>{
    setHidden(prev=>{
      const next=new Set(prev);next.add(id);
      try { localStorage.setItem(HIDDEN_KEY,JSON.stringify([...next].slice(-100))); } catch { /* local preference only */ }
      return next;
    });
  },[HIDDEN_KEY]);
  const retryTask=useCallback((_id:string)=>{
    throw new Error("禁止自动重试；请先核查原任务，避免重复生成");
  },[]);
  const tasks=useMemo(()=>allTasks.filter(t=>!hidden.has(t.id)),[allTasks,hidden]);
  const stats=useMemo(()=>({
    queued:tasks.filter(t=>t.status==="queued" || t.status==="submission_unknown").length,
    running:tasks.filter(t=>t.status==="running" || t.status==="downloading").length,
    done:tasks.filter(t=>t.status==="done").length,
    failed:tasks.filter(t=>t.status==="failed").length,
    todayCost:mode === "real" ? null : 0,total:tasks.length,tick:0,
  }),[tasks,mode]);
  return {tasks,createTask,retryTask,removeTask,stats,error,pending,recoverPending,forgetPending,service};
}
