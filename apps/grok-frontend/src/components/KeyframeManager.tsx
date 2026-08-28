import type { KeyframeScene } from '../lib/types';
import { genId } from '../lib/imageUtils';
import ImageUploadSlot from './ImageUploadSlot';

interface Props {
  scenes: KeyframeScene[];
  onChange: (scenes: KeyframeScene[]) => void;
}

const MAX_SCENES = 6;
const MIN_SCENES = 2;

export default function KeyframeManager({ scenes, onChange }: Props) {
  function updateScene(id: string, url: string, fileName?: string) {
    onChange(scenes.map((s) => (s.id === id ? { ...s, imageUrl: url, fileName } : s)));
  }

  function removeScene(id: string) {
    if (scenes.length <= MIN_SCENES) return;
    onChange(scenes.filter((s) => s.id !== id));
  }

  function addScene() {
    if (scenes.length >= MAX_SCENES) return;
    onChange([...scenes, { id: genId('scene'), imageUrl: '', fileName: '' }]);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-500">
          多关键帧模式下，每个场景都可以独立上传图片来延续任务，至少需要 {MIN_SCENES} 张，最多 {MAX_SCENES} 张。
        </p>
        <button
          type="button"
          onClick={addScene}
          disabled={scenes.length >= MAX_SCENES}
          className="shrink-0 rounded-md border border-indigo-300 px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-40"
        >
          + 添加场景
        </button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {scenes.map((scene, idx) => (
          <ImageUploadSlot
            key={scene.id}
            label={`场景 ${idx + 1} 关键帧`}
            imageUrl={scene.imageUrl}
            fileName={scene.fileName}
            onChange={(url, fileName) => updateScene(scene.id, url, fileName)}
            onRemove={scenes.length > MIN_SCENES ? () => removeScene(scene.id) : undefined}
            compact
          />
        ))}
      </div>
    </div>
  );
}
