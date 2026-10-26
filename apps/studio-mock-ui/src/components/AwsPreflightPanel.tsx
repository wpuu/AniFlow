import { useCallback, useEffect, useState } from "react";
import { Cloud, RefreshCw, ShieldAlert, X } from "lucide-react";
import type { StudioMode } from "../types";

type Verification = boolean | null;
type CheckKey =
  | "credit_ec2_eligible"
  | "credit_expiry_confirmed"
  | "tokyo_gpu_quota"
  | "tokyo_capacity_and_price"
  | "ssm_private_connectivity"
  | "h3_license_territory"
  | "gpu_stop_safeguard"
  | "credit_workspaces_eligible"
  | "tokyo_workspaces_quota"
  | "independent_stop_safeguard"
  | "account_plan_unchanged"
  | "credit_gamelift_eligible"
  | "tokyo_gamelift_quota"
  | "private_s3_connectivity"
  | "runtime_cuda_verified"
  | "workspaces_account_eligible";

interface CloudPreflight {
  mode: string;
  service?: string;
  region: string;
  instance_type: string;
  account_plan: string;
  estimated_credit_remaining_usd?: number | null;
  credit_settled_remaining_usd?: number | null;
  credit_observed_at_utc?: string | null;
  hourly_price_usd: number | null;
  expected_gpu?: string;
  expected_gpu_vram_gib?: number;
  expected_ram_gib?: number;
  checks: Partial<Record<CheckKey, Verification>>;
  launch_allowed: boolean;
  real_gpu_connected: boolean;
  tunnel_connected?: boolean;
  aws_queries: number;
  aws_writes: number;
  note?: string;
  blocked_reasons?: string[];
}

const MOCK_CHECKS: { key: CheckKey; label: string; detail: string }[] = [
  { key: "credit_ec2_eligible", label: "赠金适用 EC2", detail: "查看账户中这笔赠金的 Eligible Services" },
  { key: "credit_expiry_confirmed", label: "到期日与可用余额", detail: "以 AWS 账单控制台的最新数值为准" },
  { key: "tokyo_gpu_quota", label: "东京 G/VT 按需配额", detail: "至少需要8 vCPU；配额不足则不能启动" },
  { key: "tokyo_capacity_and_price", label: "实例库存与实时价格", detail: "核对 ap-northeast-1 的 g6e.2xlarge" },
  { key: "ssm_private_connectivity", label: "SSM 私有连接", detail: "禁公开8188；优先 Session Manager 端口转发" },
  { key: "h3_license_territory", label: "H3 使用地域与许可", detail: "核对开放权重许可、商业用途和用户所在地" },
  { key: "gpu_stop_safeguard", label: "预算与停机保护", detail: "预算告警不能代替预先配置的定时停机" },
];

const WORKSPACES_CHECKS: { key: CheckKey; label: string; detail: string }[] = [
  { key: "credit_workspaces_eligible", label: "赠金适用 WorkSpaces", detail: "核对本笔赠金的适用服务与费用项目" },
  { key: "credit_expiry_confirmed", label: "到期日与预计余额", detail: "展示已核验的账单估算快照，不是实时可用余额" },
  { key: "tokyo_workspaces_quota", label: "东京 WorkSpaces Graphics G6 配额", detail: "使用 WorkSpaces 独立配额核验结果" },
  { key: "tokyo_capacity_and_price", label: "桌面容量与费用", detail: "核对东京 Graphics.g6.4xlarge 与完整费用项目" },
  { key: "ssm_private_connectivity", label: "SSM 私有连接", detail: "通过私有隧道访问 ComfyUI，禁止公网开放8188" },
  { key: "h3_license_territory", label: "H3 使用地域与许可", detail: "核对模型许可与实际使用地域" },
  { key: "gpu_stop_safeguard", label: "定时停机保护", detail: "限制GPU运行时长；停机不代表所有费用归零" },
  { key: "independent_stop_safeguard", label: "独立备用停机", detail: "本机断网时仍能生效的第二停止措施" },
  { key: "account_plan_unchanged", label: "账户计划保持不变", detail: "不得擅自升级付费计划" },
  { key: "workspaces_account_eligible", label: "WorkSpaces 账户资格", detail: "核对本账户使用目标桌面的资格" },
];

const GAMELIFT_CHECKS: { key: CheckKey; label: string; detail: string }[] = [
  { key: "credit_gamelift_eligible", label: "赠金适用 GameLift Streams", detail: "核对赠金服务清单及实验费用" },
  { key: "credit_expiry_confirmed", label: "到期日与预计余额", detail: "账单估算快照，不是实时余额" },
  { key: "tokyo_gamelift_quota", label: "东京 Gen6n GPU 配额", detail: "配额显示值还需真实容量分配验证" },
  { key: "tokyo_capacity_and_price", label: "容量与费用", detail: "东京 gen6n_pro；释放分配容量后结束 GPU 计费" },
  { key: "private_s3_connectivity", label: "私有 S3 保存与恢复", detail: "结果私有保存，本机按字节数和 SHA256 恢复下载" },
  { key: "h3_license_territory", label: "H3 使用地域与许可", detail: "东京运行，中国大陆使用和展示" },
  { key: "gpu_stop_safeguard", label: "东京定时释放", detail: "固定截止时间删除目标流组并核验释放" },
  { key: "independent_stop_safeguard", label: "新加坡独立备用释放", detail: "SSM 独立执行，不依赖本机在线" },
  { key: "account_plan_unchanged", label: "账户计划保持不变", detail: "不升级计划，不申请增加配额" },
  { key: "runtime_cuda_verified", label: "真实 CUDA 与运行环境", detail: "需实际 GPU、量化内核和工作流节点核验" },
];

function checklist(service: string | undefined, mode: StudioMode) {
  return mode === "real" ? (service === "gameliftstreams" ? GAMELIFT_CHECKS : WORKSPACES_CHECKS) : MOCK_CHECKS;
}

export function parseCloudPreflight(body: unknown, mode: StudioMode): CloudPreflight {
  if (!body || typeof body !== "object" || !("checks" in body)) {
    throw new Error("无效的 AWS 预检返回");
  }
  const value = body as CloudPreflight;
  const checks = checklist(value.service, mode);
  if (typeof value.launch_allowed !== "boolean" || typeof value.real_gpu_connected !== "boolean"
      || !value.checks || !checks.every(c => Object.prototype.hasOwnProperty.call(value.checks, c.key)
        && (value.checks[c.key] === true || value.checks[c.key] === false || value.checks[c.key] === null))) {
    throw new Error("AWS 预检返回缺少必要安全字段");
  }
  if (mode === "real" && (value.mode !== "LOCAL_AUDIT_PROJECTION" || !["workspaces", "gameliftstreams"].includes(value.service ?? ""))) {
    throw new Error("真实预检必须返回已支持服务的本机审计投影");
  }
  if (mode === "real") {
    for (const amount of [value.estimated_credit_remaining_usd, value.credit_settled_remaining_usd]) {
      if (amount != null && (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0)) {
        throw new Error("赠金预计或结算余额格式无效");
      }
    }
  }
  return value;
}

function Status({ value }: { value: Verification }) {
  if (value === true) return <span className="text-emerald-300">已验证</span>;
  if (value === false) return <span className="text-rose-300">未通过</span>;
  return <span className="text-amber-300">未核验</span>;
}

export function AwsPreflightPanel({ onClose, mode }: { onClose: () => void; mode:StudioMode }) {
  const [data, setData] = useState<CloudPreflight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/studio/cloud/preflight", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      setData(parseCloudPreflight(await response.json(), mode));
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => { void refresh(); }, [refresh]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/75 px-3 py-6"
      role="dialog" aria-modal="true" aria-label="AWS 东京部署预检" data-testid="aws-preflight-panel">
      <section className="w-full max-w-2xl rounded-2xl border border-white/10 bg-[#131319] text-zinc-200 shadow-2xl">
        <header className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div className="flex items-center gap-2">
            <Cloud className="h-5 w-5 text-cyan-300" />
            <div>
              <h2 className="font-semibold">AWS 东京 H3 部署预检</h2>
              <p className="text-xs text-zinc-400">只读核验入口 · 这里不提供创建或启动实例操作</p>
            </div>
          </div>
          <button type="button" aria-label="关闭 AWS 预检" onClick={onClose}
            className="rounded-lg p-2 text-zinc-400 hover:bg-white/10 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="space-y-4 px-5 py-4">
          <div className="flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-950/30 p-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <p className="text-xs leading-relaxed text-amber-100">
              {data?.mode === "UNVERIFIED_PLACEHOLDER"
                ? "当前连接的是本机模拟 Bridge，并未读取你的 AWS 账户。所有资格、赠金余额及实例价格均为未知，不能据此开机。"
                : mode === "real"
                  ? "账户资格与余额来自已保存的核验结果。目标规格不代表实测设备；真实生成仍需当前 GPU 连接和双重停机保护。"
                  : "只有 AWS 账户核验并落实定时停机与独立备用措施后，才可创建 GPU 实例。"}
            </p>
          </div>
          <div className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs sm:grid-cols-2">
            <div>目标区域 <span className="font-mono text-cyan-200">{data?.region ?? "ap-northeast-1"}</span></div>
            <div>目标规格 <span className="font-mono text-cyan-200">{data?.instance_type ?? (mode === "real" ? "Graphics.g6.4xlarge" : "g6e.2xlarge")}</span></div>
            <div>账户计划 <span className="text-amber-300">{data?.account_plan === "unknown" || !data ? "未知" : data.account_plan}</span></div>
            <div>赠金预计余额 <span className="text-amber-300">{data?.estimated_credit_remaining_usd == null ? "尚未核验" : "$" + data.estimated_credit_remaining_usd.toFixed(2)}</span></div>
            {mode === "real" && <>
              <div>结算余额 <span className="text-zinc-400">{data?.credit_settled_remaining_usd == null ? "尚未核验" : "$" + data.credit_settled_remaining_usd.toFixed(2)}</span></div>
              <div>核验时间（UTC） <span className="text-zinc-400">{data?.credit_observed_at_utc ?? "尚未核验"}</span></div>
              <div className="sm:col-span-2">目标硬件（未实测） <span className="text-cyan-200">{data?.expected_gpu ?? "NVIDIA L4"} / {data?.expected_gpu_vram_gib ?? 24}GiB 显存 / {data?.expected_ram_gib ?? 64}GiB 内存</span></div>
            </>}
          </div>
          <div className="space-y-1" data-testid="aws-preflight-checklist">
            {checklist(data?.service, mode).map((c) => (
              <div key={c.key} className="flex justify-between gap-3 border-b border-white/5 py-2.5">
                <div>
                  <p className="text-xs font-medium">{c.label}</p>
                  <p className="mt-1 text-[11px] text-zinc-500">{c.detail}</p>
                </div>
                <div className="shrink-0 text-xs"><Status value={data?.checks[c.key] ?? null} /></div>
              </div>
            ))}
          </div>
          {error && <p role="alert" className="text-xs text-rose-300">无法读取本机预检接口：{error}</p>}
          {mode === "real" && data?.note && <p className="text-xs text-zinc-400">{data.note}</p>}
          {mode === "real" && data?.blocked_reasons && data.blocked_reasons.length > 0 && <ul className="list-disc space-y-1 pl-4 text-xs text-amber-300">
            {data.blocked_reasons.map(reason => <li key={reason}>{reason}</li>)}
          </ul>}
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] text-zinc-500">
              {mode === "real" ? "此面板只读；资格、预算与停机保护未通过时禁止真实生成。" : "EC2 控制保持关闭；本机 Studio 只执行不收费的模拟任务。"}
            </p>
            <button type="button" onClick={() => void refresh()} disabled={loading}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-white/15 px-3 py-2 text-xs hover:bg-white/5 disabled:opacity-50">
              <RefreshCw className="h-3.5 w-3.5" /> {loading ? "读取中" : "刷新预检"}
            </button>
          </div>
          <div className="rounded-lg bg-zinc-900 px-3 py-2 text-xs text-zinc-400" data-testid="aws-launch-disabled">
            {mode === "real" ? "WorkSpaces 创建、启动与恢复不在此页面执行。预计余额与核验时间来自本机审计快照；真实生成以本机服务的完整预检为准。" : "AWS 创建、开机和真实生成：未授权 / 未接入。此页面无法执行计费操作。"}
          </div>
        </div>
      </section>
    </div>
  );
}
