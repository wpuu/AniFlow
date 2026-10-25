import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CreatePayload, Task } from "../types";

const API = "/api/studio/mock";
const HIDDEN_KEY = "aniflow.mock.hidden_ids.v1";
interface ServerJob {
  id: string; project_id: string; shot_id: string; image_id: string;
  prompt: string; negative_prompt: string; aspect_ratio: Task["aspectRatio"];
  duration_seconds: number; provider: string; created_at: number;
  status: "queued" | "running" | "completed" | "failed";
  progress: number; video_download_path: string | null;
  actual_cost_usd: number; simulation: boolean; gpu_connected: boolean;
}
function toTask(job: ServerJob): Task {
  if (job.simulation !== true || job.gpu_connected !== false || job.provider !== "mock-h3") {
    throw new Error("服务返回非模拟任务，已拒绝混入 Mock 历史");
  }
  return {
    id: job.id, prompt: job.prompt, negativePrompt: job.negative_prompt,
    modelId: "mock-h3", aspectRatio: job.aspect_ratio,
    duration: job.duration_seconds, fps: 24, seed: 0, cfg: 0, motion: 0,
    status: job.status === "completed" ? "done" : job.status,
    progress: job.progress, etaSeconds: Math.max(0, Math.ceil(6 - (Date.now()/1000 - job.created_at))),
    cost: 0, createdAt: job.created_at*1000,
    firstFrame: API + "/assets/" + job.image_id,
    thumbnailUrl: API + "/assets/" + job.image_id,
    videoUrl: job.video_download_path ?? undefined,
  };
}
async function jsonOrError(res: Response): Promise<any> {
  let body: any;
  try { body = await res.json(); } catch { throw new Error("本机 Mock Bridge 返回无法解析的响应"); }
  if (!res.ok) throw new Error(typeof body?.detail === "string" ? body.detail : "HTTP " + res.status);
  return body;
}
export function useTaskEngine() {
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(HIDDEN_KEY) || "[]");
      return new Set(Array.isArray(v) ? v.filter((i)=>typeof i==="string") : []);
    } catch { return new Set(); }
  });
  const [error, setError] = useState<string|null>(null);
  const submitting = useRef(false);
  const refresh = useCallback(async () => {
    const response = await fetch(API + "/jobs?limit=100", {cache: "no-store"});
    const body = await jsonOrError(response);
    if (body.simulation !== true || !Array.isArray(body.jobs)) {
      throw new Error("服务器不是预期的本机 Mock Bridge");
    }
    setAllTasks(body.jobs.map(toTask));
    setError(null);
  }, []);
  useEffect(() => {
    void refresh().catch(e=>setError(String(e)));
    const id=window.setInterval(()=>{void refresh().catch(e=>setError(String(e)));},1600);
    return ()=>window.clearInterval(id);
  },[refresh]);

  const createTask = useCallback(async(payload:CreatePayload):Promise<Task>=>{
    if (submitting.current) throw new Error("上次提交仍在进行，未创建重复任务");
    if (!payload.firstFrame?.startsWith("data:image/")) {
      throw new Error("请先上传电脑中的 PNG/JPG 首帧，示例网络图片不能提交");
    }
    submitting.current = true;
    try {
      const blob = await fetch(payload.firstFrame).then(r=>r.blob());
      if (blob.size > 10*1024*1024) throw new Error("首帧超过10MB");
      const filename = blob.type === "image/png" ? "frame.png" : "frame.jpg";
      const form = new FormData();
      form.append("file",blob,filename);
      const asset=await jsonOrError(await fetch(API + "/assets", {method:"POST",body:form}));
      const key = typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : "mock-" + Date.now() + "-" + Math.random().toString(36).slice(2);
      const result:ServerJob = await jsonOrError(await fetch(API + "/jobs",{
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          project_id:"SnowDirector", shot_id:"MYCL001-01",
          image_id:asset.image_id, prompt:payload.prompt,
          negative_prompt:payload.negativePrompt,
          duration_seconds:payload.duration, aspect_ratio:payload.aspectRatio,
          idempotency_key:key, provider:"mock-h3",
        }),
      }));
      if (!result.simulation) throw new Error("非模拟响应已拒绝");
      const created=toTask(result);
      setAllTasks(prev=>[created,...prev.filter(t=>t.id!==created.id)]);
      return created;
    } finally {
      submitting.current = false;
    }
  },[]);

  const removeTask=useCallback((id:string)=>{
    setHidden(prev=>{
      const next=new Set(prev);next.add(id);
      try { localStorage.setItem(HIDDEN_KEY,JSON.stringify([...next].slice(-100))); } catch { /* local preference only */ }
      return next;
    });
  },[]);
  const retryTask=useCallback((_id:string)=>{
    throw new Error("Mock阶段禁用自动重试；请重新确认首帧并手动提交新任务");
  },[]);
  const tasks=useMemo(()=>allTasks.filter(t=>!hidden.has(t.id)),[allTasks,hidden]);
  const stats=useMemo(()=>({
    queued:tasks.filter(t=>t.status==="queued").length,
    running:tasks.filter(t=>t.status==="running").length,
    done:tasks.filter(t=>t.status==="done").length,
    failed:tasks.filter(t=>t.status==="failed").length,
    todayCost:0,total:tasks.length,tick:0,
  }),[tasks]);
  return {tasks,createTask,retryTask,removeTask,stats,error};
}
