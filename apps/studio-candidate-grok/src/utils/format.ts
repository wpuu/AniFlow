export function formatCost(value: number) {
  return `$${value.toFixed(3)}`;
}

export function formatEta(seconds: number) {
  if (seconds <= 0) return "—";
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.ceil(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function formatClock(ts: number) {
  return new Date(ts).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function formatDate(ts: number) {
  return new Date(ts).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function relativeTime(ts: number) {
  const diff = Math.max(0, Date.now() - ts);
  const sec = Math.floor(diff / 1000);
  if (sec < 10) return "刚刚";
  if (sec < 60) return `${sec} 秒前`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  return `${Math.floor(hr / 24)} 天前`;
}

export function uid(prefix = "AF") {
  const hex = Math.random().toString(16).slice(2, 6).toUpperCase();
  return `${prefix}-${hex}`;
}
