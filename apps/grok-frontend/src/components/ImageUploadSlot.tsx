import { useRef, useState } from 'react';
import { fileToResizedDataUrl } from '../lib/imageUtils';
import { cn } from '../utils/cn';

interface Props {
  label: string;
  imageUrl: string;
  fileName?: string;
  onChange: (url: string, fileName?: string) => void;
  onRemove?: () => void;
  compact?: boolean;
}

export default function ImageUploadSlot({ label, imageUrl, fileName, onChange, onRemove, compact }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleFile(file: File | null) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError('请选择图片文件');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const dataUrl = await fileToResizedDataUrl(file);
      onChange(dataUrl, file.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : '图片处理失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50/60 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-600">{label}</span>
        {onRemove ? (
          <button type="button" onClick={onRemove} className="text-xs text-rose-500 hover:underline">
            移除场景
          </button>
        ) : null}
      </div>
      <div className={cn('flex gap-3', compact ? 'flex-col' : 'flex-col sm:flex-row')}>
        <div
          className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-md border border-zinc-200 bg-white"
        >
          {imageUrl ? (
            <img src={imageUrl} alt={label} className="h-full w-full object-cover" />
          ) : (
            <span className="px-2 text-center text-[11px] text-zinc-400">暂无图片</span>
          )}
        </div>
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.currentTarget.files?.[0] ?? null;
                void handleFile(file);
                e.currentTarget.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={loading}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? '处理中…' : '上传图片'}
            </button>
            <button
              type="button"
              onClick={() => setShowUrlInput((v) => !v)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100"
            >
              {showUrlInput ? '收起链接输入' : '填写图片URL'}
            </button>
            {imageUrl ? (
              <button
                type="button"
                onClick={() => {
                  setError('');
                  onChange('', '');
                }}
                className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-500 hover:bg-zinc-100"
              >
                清除图片
              </button>
            ) : null}
          </div>
          {showUrlInput ? (
            <input
              type="text"
              value={imageUrl.startsWith('data:') ? '' : imageUrl}
              onChange={(e) => {
                setError('');
                onChange(e.target.value, undefined);
              }}
              placeholder="https://example.com/image.png"
              className="w-full rounded-md border border-zinc-300 px-2 py-1.5 text-xs outline-none focus:border-indigo-500"
            />
          ) : null}
          {fileName ? <span className="truncate text-[11px] text-zinc-400">已上传：{fileName}</span> : null}
          {error ? <span className="text-[11px] text-rose-500">{error}</span> : null}
        </div>
      </div>
    </div>
  );
}
