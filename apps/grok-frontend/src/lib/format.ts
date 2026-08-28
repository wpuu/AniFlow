export function formatTime(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const MODE_LABELS: Record<string, string> = {
  t2v: '文生视频',
  i2v: '图生视频',
  keyframes: '多关键帧',
};

export function modeLabel(mode: string): string {
  return MODE_LABELS[mode] || mode;
}
