import { useCallback, useEffect, useState } from "react";
import { Cloud, RefreshCw, ShieldAlert, X } from "lucide-react";

type Verification = boolean | null;
type CheckKey =
  | "credit_ec2_eligible"
  | "credit_expiry_confirmed"
  | "tokyo_gpu_quota"
  | "tokyo_capacity_and_price"
  | "ssm_private_connectivity"
  | "h3_license_territory"
  | "gpu_stop_safeguard";

interface CloudPreflight {
  mode: string;
  region: string;
  instance_type: string;
  account_plan: string;
  actual_credit_usd: number | null;
  hourly_price_usd: number | null;
  checks: Record<CheckKey, Verification>;
  launch_allowed: boolean;
  real_gpu_connected: boolean;
  aws_queries: number;
  aws_writes: number;
}

const CHECKS: { key: CheckKey; label: string; detail: string }[] = [
  { key: "credit_ec2_eligible", label: "赠金适用 EC2", detail: "查看账户中这笔赠金的 Eligible Services" },
  { key: "credit_expiry_confirmed", label: "到期日与可用余额", detail: "以 AWS 账单控制台的最新数值为准" },
  { key: "tokyo_gpu_quota", label: "东京 G/VT 按需配额", detail: "至少需要8 vCPU；配额不足则不能启动" },
  { key: "tokyo_capacity_and_price", label: "实例库存与实时价格", detail: "核对 ap-northeast-1 的 g6e.2xlarge" },
  { key: "ssm_private_connectivity", label: "SSM 私有连接", detail: "禁公开8188；优先 Session Manager 端口转发" },
  { key: "h3_license_territory", label: "H3 使用地域与许可", detail: "核对开放权重许可、商业用途和用户所在地" },
  { key: "gpu_stop_safeguard", label: "预算与停机保护", detail: "预算告警不能代替预先配置的定时停机" },
];

function Status({ value }: { value: Verification }) {
  if (value === true) return <span className="text-emerald-300">已验证</span>;
  if (value === false) return <span className="text-rose-300">未通过</span>;
  return <span className="text-amber-300">未核验</span>;
}

export function AwsPreflightPanel({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<CloudPreflight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/studio/cloud/preflight", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const body: unknown = await response.json();
      if (!body || typeof body !== "object" || !("checks" in body)) {
        throw new Error("无效的 AWS 预检返回");
      }
      const value = body as CloudPreflight;
      if (typeof value.launch_allowed !== "boolean" ||
          typeof value.real_gpu_connected !== "boolean" ||
          !value.checks || !CHECKS.every((c) => Object.prototype.hasOwnProperty.call(value.checks, c.key))) {
        throw new Error("AWS 预检返回缺少必要安全字段");
      }
      setData(value);
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/75 px-3 py-6 sm:items-center"
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
                : "只有 AWS 账户实时核验并落实停止计费的保护后，才可单独授权创建 GPU 实例。"}
            </p>
          </div>
          <div className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs sm:grid-cols-2">
            <div>目标区域 <span className="font-mono text-cyan-200">{data?.region ?? "ap-northeast-1"}</span></div>
            <div>目标规格 <span className="font-mono text-cyan-200">{data?.instance_type ?? "g6e.2xlarge"}</span></div>
            <div>账户计划 <span className="text-amber-300">{data?.account_plan === "unknown" || !data ? "未知" : data.account_plan}</span></div>
            <div>赠金余额 <span className="text-amber-300">{data?.actual_credit_usd == null ? "尚未读取" : "$" + data.actual_credit_usd.toFixed(2)}</span></div>
          </div>
          <div className="space-y-1" data-testid="aws-preflight-checklist">
            {CHECKS.map((c) => (
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
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] text-zinc-500">
              EC2 控制保持关闭；本机 Studio 只执行不收费的模拟任务。
            </p>
            <button type="button" onClick={() => void refresh()} disabled={loading}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-white/15 px-3 py-2 text-xs hover:bg-white/5 disabled:opacity-50">
              <RefreshCw className="h-3.5 w-3.5" /> {loading ? "读取中" : "刷新预检"}
            </button>
          </div>
          <div className="rounded-lg bg-zinc-900 px-3 py-2 text-xs text-zinc-400" data-testid="aws-launch-disabled">
            AWS 创建、开机和真实生成：未授权 / 未接入。此页面无法执行计费操作。
          </div>
        </div>
      </section>
    </div>
  );
}
