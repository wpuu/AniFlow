import { useCallback, useEffect, useRef, useState } from 'react';
import KeySettings from './components/KeySettings';
import GenerateBar from './components/GenerateBar';
import SettingsForm from './components/SettingsForm';
import RightPanel from './components/RightPanel';
import CollapsibleSection from './components/CollapsibleSection';
import { STORAGE_KEYS, loadJSON, saveJSON } from './lib/storage';
import { DEFAULT_PARAMS_BY_MODEL, VIDEO_MODELS } from './lib/constants';
import { createVideoTask, getVideoResult } from './lib/api';
import { genId } from './lib/imageUtils';
import type {
  GenerationParams,
  HistoryItem,
  TaskState,
  TaskStatus,
  VideoModelKey,
} from './lib/types';

const BUSY_STATUSES = new Set<TaskStatus>(['creating', 'queued', 'in_progress']);

function emptyTask(): TaskState {
  return { status: 'idle', progress: 0, videoUrl: null, videoId: null, taskId: null, error: null };
}

function mapStatus(status?: string): TaskStatus {
  if (status === 'queued' || status === 'in_progress' || status === 'completed' || status === 'failed') {
    return status;
  }
  return 'queued';
}

function isPublicImageUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
}

function mergeParams(
  base: GenerationParams,
  saved: Partial<GenerationParams> | null | undefined,
): GenerationParams {
  return {
    ...base,
    ...(saved || {}),
    keyframeScenes:
      saved?.keyframeScenes?.length ? saved.keyframeScenes : base.keyframeScenes,
  };
}

export default function App() {
  const [apiKeyCount, setApiKeyCount] = useState<number>(() => loadJSON(STORAGE_KEYS.KEY_COUNT, 1));
  const [apiKeys, setApiKeys] = useState<string[]>(() => {
    const saved = loadJSON<string[]>(STORAGE_KEYS.API_KEYS, []);
    const count = loadJSON(STORAGE_KEYS.KEY_COUNT, 1);
    return Array.from({ length: count }, (_, i) => saved[i] ?? '');
  });

  const [modelKey, setModelKey] = useState<VideoModelKey>(() =>
    loadJSON<VideoModelKey>(STORAGE_KEYS.ACTIVE_MODEL, 'v2'),
  );

  const [paramsByModel, setParamsByModel] = useState<Record<VideoModelKey, GenerationParams>>(() => {
    const saved = loadJSON<Partial<Record<VideoModelKey, GenerationParams>>>(STORAGE_KEYS.PARAMS_BY_MODEL, {});
    const legacy = loadJSON<GenerationParams | null>(STORAGE_KEYS.LAST_PARAMS, null);
    return {
      v2: mergeParams(DEFAULT_PARAMS_BY_MODEL.v2, saved.v2 ?? legacy),
      flash25: mergeParams(DEFAULT_PARAMS_BY_MODEL.flash25, saved.flash25),
    };
  });

  const params = paramsByModel[modelKey];

  const [tasksByKey, setTasksByKey] = useState<Record<number, TaskState>>({});
  const [history, setHistory] = useState<HistoryItem[]>(() => loadJSON(STORAGE_KEYS.HISTORY, []));
  const [selectedKeyTab, setSelectedKeyTab] = useState(0);
  const [selectedHistoryIdByKey, setSelectedHistoryIdByKey] = useState<Record<number, string | undefined>>({});
  const [message, setMessage] = useState<{ text: string; type: 'info' | 'error' } | null>(null);

  const pollTimers = useRef<Record<number, number>>({});
  const stopFlags = useRef<Record<number, boolean>>({});
  const activeHistoryIdByKey = useRef<Record<number, string>>({});

  useEffect(() => {
    saveJSON(STORAGE_KEYS.API_KEYS, apiKeys);
  }, [apiKeys]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.KEY_COUNT, apiKeyCount);
  }, [apiKeyCount]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.ACTIVE_MODEL, modelKey);
  }, [modelKey]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.HISTORY, history.slice(0, 300));
  }, [history]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      saveJSON(STORAGE_KEYS.PARAMS_BY_MODEL, paramsByModel);
      saveJSON(STORAGE_KEYS.LAST_PARAMS, paramsByModel.v2);
    }, 500);
    return () => window.clearTimeout(t);
  }, [paramsByModel]);

  useEffect(() => {
    if (!message) return;
    const t = window.setTimeout(() => setMessage(null), 4500);
    return () => window.clearTimeout(t);
  }, [message]);

  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach((id) => window.clearTimeout(id));
    };
  }, []);

  function notify(text: string, type: 'info' | 'error' = 'info') {
    setMessage({ text, type });
  }

  function updateTaskState(keyIndex: number, patch: Partial<TaskState>) {
    setTasksByKey((prev) => ({ ...prev, [keyIndex]: { ...(prev[keyIndex] ?? emptyTask()), ...patch } }));
  }

  function updateHistoryItem(id: string, patch: Partial<HistoryItem>) {
    setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, ...patch } : h)));
  }

  function updateParams(updater: (prev: GenerationParams) => GenerationParams) {
    setParamsByModel((prev) => ({
      ...prev,
      [modelKey]: updater(prev[modelKey]),
    }));
  }

  function handleModelChange(nextModel: VideoModelKey) {
    setModelKey(nextModel);
    notify(`已切换到 ${VIDEO_MODELS[nextModel].label}，该模型上次设置已恢复`);
  }

  function handleKeyCountChange(count: number) {
    setApiKeyCount(count);
    setApiKeys((prev) => Array.from({ length: count }, (_, i) => prev[i] ?? ''));
    setSelectedKeyTab((prev) => Math.min(prev, count - 1));
  }

  function handleKeyChange(index: number, value: string) {
    setApiKeys((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
  }

  const poll = useCallback(
    (
      keyIndex: number,
      apiKey: string,
      videoId: string,
      historyId: string,
      taskModelKey: VideoModelKey,
      retriesLeft = 5,
    ) => {
      const run = async () => {
        if (stopFlags.current[keyIndex]) return;
        try {
          const result = await getVideoResult(apiKey, videoId, taskModelKey);
          if (stopFlags.current[keyIndex]) return;
          const status = mapStatus(result.status);
          const patch: Partial<TaskState> = {
            status,
            progress: result.progress ?? 0,
            size: result.size,
            seconds: result.seconds,
            modelKey: taskModelKey,
          };
          if (status === 'completed') {
            patch.videoUrl = result.metadata?.url ?? null;
            patch.progress = 100;
          }
          if (status === 'failed') {
            patch.error = result.error?.message || '生成失败，请检查参数或稍后重试';
          }
          updateTaskState(keyIndex, patch);
          updateHistoryItem(historyId, patch as Partial<HistoryItem>);

          if (status === 'completed' || status === 'failed') {
            delete pollTimers.current[keyIndex];
            delete activeHistoryIdByKey.current[keyIndex];
            return;
          }
          pollTimers.current[keyIndex] = window.setTimeout(
            () => poll(keyIndex, apiKey, videoId, historyId, taskModelKey, 5),
            3000,
          );
        } catch (err) {
          if (stopFlags.current[keyIndex]) return;
          if (retriesLeft > 0) {
            pollTimers.current[keyIndex] = window.setTimeout(
              () => poll(keyIndex, apiKey, videoId, historyId, taskModelKey, retriesLeft - 1),
              4000,
            );
          } else {
            const msg = err instanceof Error ? err.message : '网络异常，查询进度失败';
            updateTaskState(keyIndex, { status: 'failed', error: msg, modelKey: taskModelKey });
            updateHistoryItem(historyId, { status: 'failed', error: msg });
            delete activeHistoryIdByKey.current[keyIndex];
          }
        }
      };
      run();
    },
    [],
  );

  const startGeneration = useCallback(
    async (keyIndex: number) => {
      const apiKey = apiKeys[keyIndex]?.trim();
      if (!apiKey) {
        notify(`请先填写 Key ${keyIndex + 1}`, 'error');
        return;
      }
      if (!params.prompt.trim()) {
        notify('请先填写提示词', 'error');
        return;
      }

      if (params.mode === 'i2v' && !params.singleImage) {
        notify('图生视频模式需要先上传图片或填写图片地址', 'error');
        return;
      }

      if (modelKey === 'flash25') {
        if (params.mode === 'i2v' && !isPublicImageUrl(params.singleImage)) {
          notify('2.5 Flash 当前首帧需要可公开访问的 http(s) 图片 URL；本地图片需先上传到媒体存储', 'error');
          return;
        }
        if (params.mode === 'keyframes') {
          const images = params.keyframeScenes.map((s) => s.imageUrl.trim()).filter(Boolean);
          if (images.length < 2) {
            notify('2.5 Flash 首尾帧模式需要首帧和尾帧两张图片', 'error');
            return;
          }
          if (!images.slice(0, 2).every(isPublicImageUrl)) {
            notify('2.5 Flash 首尾帧需要可公开访问的 http(s) 图片 URL', 'error');
            return;
          }
        }
      } else if (params.mode === 'keyframes') {
        const valid = params.keyframeScenes.filter((s) => s.imageUrl.trim());
        if (valid.length < 2) {
          notify('V2.0 多关键帧模式至少需要上传 2 张关键帧图片', 'error');
          return;
        }
      }

      stopFlags.current[keyIndex] = false;

      const historyId = genId('task');
      activeHistoryIdByKey.current[keyIndex] = historyId;
      setSelectedKeyTab(keyIndex);

      const modelName = VIDEO_MODELS[modelKey].apiModel;
      const newItem: HistoryItem = {
        id: historyId,
        keyIndex,
        createdAt: Date.now(),
        promptPreview: params.prompt.trim().slice(0, 100),
        modelKey,
        modelName,
        mode: params.mode,
        ratio: params.ratio,
        resolution: params.resolution,
        status: 'creating',
        progress: 0,
        videoUrl: null,
        videoId: null,
        taskId: null,
      };
      setHistory((prev) => [newItem, ...prev]);
      setSelectedHistoryIdByKey((prev) => ({ ...prev, [keyIndex]: historyId }));
      updateTaskState(keyIndex, {
        status: 'creating',
        progress: 0,
        videoUrl: null,
        videoId: null,
        taskId: null,
        error: null,
        modelKey,
      });

      try {
        const created = await createVideoTask(apiKey, modelKey, params);
        const videoId = created.video_id || created.id || created.task_id || '';
        const taskId = created.task_id || created.id || '';
        if (!videoId) throw new Error('未获取到有效的视频任务 ID，请检查返回结果');
        const status = mapStatus(created.status);
        updateTaskState(keyIndex, { status, progress: created.progress ?? 0, videoId, taskId, modelKey });
        updateHistoryItem(historyId, { status, progress: created.progress ?? 0, videoId, taskId });
        poll(keyIndex, apiKey, videoId, historyId, modelKey);
      } catch (err) {
        const msg = err instanceof Error ? err.message : '创建任务失败';
        updateTaskState(keyIndex, { status: 'failed', error: msg, modelKey });
        updateHistoryItem(historyId, { status: 'failed', error: msg });
        delete activeHistoryIdByKey.current[keyIndex];
        notify(msg, 'error');
      }
    },
    [apiKeys, modelKey, params, poll],
  );

  function stopGeneration(keyIndex: number) {
    stopFlags.current[keyIndex] = true;
    const t = pollTimers.current[keyIndex];
    if (t) {
      window.clearTimeout(t);
      delete pollTimers.current[keyIndex];
    }
    setTasksByKey((prev) => {
      const cur = prev[keyIndex];
      if (!cur || cur.status === 'completed' || cur.status === 'failed') return prev;
      return { ...prev, [keyIndex]: { ...cur, status: 'stopped' } };
    });

    const activeId = activeHistoryIdByKey.current[keyIndex];
    if (activeId) {
      setHistory((prev) =>
        prev.map((h) =>
          h.id === activeId && h.status !== 'completed' && h.status !== 'failed'
            ? { ...h, status: 'stopped' }
            : h,
        ),
      );
      delete activeHistoryIdByKey.current[keyIndex];
    }
  }

  function generateAll() {
    for (let i = 0; i < apiKeyCount; i += 1) {
      const busy = BUSY_STATUSES.has(tasksByKey[i]?.status ?? 'idle');
      if (!busy && apiKeys[i]?.trim()) {
        startGeneration(i);
      }
    }
  }

  function refreshHistoryItem(item: HistoryItem) {
    const apiKey = apiKeys[item.keyIndex]?.trim();
    if (!apiKey || !item.videoId) {
      notify('缺少 Key 或视频 ID，无法刷新', 'error');
      return;
    }
    const itemModelKey = item.modelKey ?? 'v2';
    getVideoResult(apiKey, item.videoId, itemModelKey)
      .then((result) => {
        const status = mapStatus(result.status);
        const patch: Partial<HistoryItem> = {
          status,
          progress: result.progress ?? item.progress,
          size: result.size,
          seconds: result.seconds,
        };
        if (status === 'completed') patch.videoUrl = result.metadata?.url ?? null;
        if (status === 'failed') patch.error = result.error?.message || '生成失败';
        updateHistoryItem(item.id, patch);

        if (activeHistoryIdByKey.current[item.keyIndex] === item.id) {
          updateTaskState(item.keyIndex, patch as Partial<TaskState>);
        }
      })
      .catch((err) => notify(err instanceof Error ? err.message : '刷新失败', 'error'));
  }

  function selectHistory(keyIndex: number, id: string) {
    setSelectedHistoryIdByKey((prev) => ({ ...prev, [keyIndex]: id }));
  }

  function handleSaveAsDefault() {
    const defaults = loadJSON<Partial<Record<VideoModelKey, GenerationParams>>>(
      STORAGE_KEYS.DEFAULT_PARAMS_BY_MODEL,
      {},
    );
    const next = { ...defaults, [modelKey]: params };
    saveJSON(STORAGE_KEYS.DEFAULT_PARAMS_BY_MODEL, next);
    if (modelKey === 'v2') saveJSON(STORAGE_KEYS.DEFAULT_PARAMS, params);
    notify(`已将 ${VIDEO_MODELS[modelKey].label} 当前设置保存为默认设置`);
  }

  function handleRestoreDefault() {
    const defaults = loadJSON<Partial<Record<VideoModelKey, GenerationParams>>>(
      STORAGE_KEYS.DEFAULT_PARAMS_BY_MODEL,
      {},
    );
    const legacyDefault =
      modelKey === 'v2' ? loadJSON<GenerationParams | null>(STORAGE_KEYS.DEFAULT_PARAMS, null) : null;
    const def = defaults[modelKey] ?? legacyDefault;
    if (def) {
      updateParams(() => mergeParams(DEFAULT_PARAMS_BY_MODEL[modelKey], def));
      notify(`已恢复 ${VIDEO_MODELS[modelKey].label} 默认设置`);
    } else {
      notify('当前模型尚未保存过默认设置', 'error');
    }
  }

  function handleRestoreLast() {
    const saved = loadJSON<Partial<Record<VideoModelKey, GenerationParams>>>(STORAGE_KEYS.PARAMS_BY_MODEL, {});
    const last = saved[modelKey];
    if (last) {
      updateParams(() => mergeParams(DEFAULT_PARAMS_BY_MODEL[modelKey], last));
      notify(`已恢复 ${VIDEO_MODELS[modelKey].label} 上一次自动保存的设置`);
    } else {
      notify('当前模型暂无已保存设置', 'error');
    }
  }

  function handleClearHistory() {
    setHistory([]);
    saveJSON(STORAGE_KEYS.HISTORY, []);
    notify('历史记录已清空');
  }

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white/95 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <rect x="3" y="5" width="18" height="14" rx="2" />
                  <path d="m10 9 5 3-5 3V9z" />
                </svg>
              </div>
              <div>
                <h1 className="text-base font-bold leading-tight text-zinc-900 sm:text-lg">
                  Agnes 视频生成工作台
                </h1>
                <p className="text-xs text-zinc-400">
                  当前：{VIDEO_MODELS[modelKey].label} · 多 Key 并行 · 模型参数独立保存
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button
                type="button"
                onClick={handleRestoreLast}
                className="rounded-md border border-zinc-300 px-2.5 py-1.5 font-medium text-zinc-600 hover:bg-zinc-100"
              >
                恢复上次内容
              </button>
              <button
                type="button"
                onClick={handleSaveAsDefault}
                className="rounded-md border border-zinc-300 px-2.5 py-1.5 font-medium text-zinc-600 hover:bg-zinc-100"
              >
                保存为默认设置
              </button>
              <button
                type="button"
                onClick={handleRestoreDefault}
                className="rounded-md border border-zinc-300 px-2.5 py-1.5 font-medium text-zinc-600 hover:bg-zinc-100"
              >
                应用默认设置
              </button>
              <button
                type="button"
                onClick={handleClearHistory}
                className="rounded-md border border-rose-200 px-2.5 py-1.5 font-medium text-rose-500 hover:bg-rose-50"
              >
                清空历史记录
              </button>
            </div>
          </div>

          <div className="mt-3">
            <GenerateBar
              keyCount={apiKeyCount}
              apiKeys={apiKeys}
              tasksByKey={tasksByKey}
              onGenerate={startGeneration}
              onStop={stopGeneration}
              onGenerateAll={generateAll}
            />
          </div>

          {message ? (
            <div
              className={`mt-2 rounded-md px-3 py-1.5 text-xs font-medium ${
                message.type === 'error' ? 'bg-rose-50 text-rose-600' : 'bg-indigo-50 text-indigo-600'
              }`}
            >
              {message.text}
            </div>
          ) : null}
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <CollapsibleSection title="API Key 设置" subtitle="配置生成所需的 API Key" defaultOpen badge={`${apiKeyCount} 个`}>
            <KeySettings
              keyCount={apiKeyCount}
              apiKeys={apiKeys}
              onKeyCountChange={handleKeyCountChange}
              onKeyChange={handleKeyChange}
            />
          </CollapsibleSection>

          <SettingsForm
            modelKey={modelKey}
            onModelChange={handleModelChange}
            params={params}
            onChange={updateParams}
          />
        </div>

        <div className="lg:col-span-1">
          <div className="lg:sticky lg:top-[9.5rem] lg:max-h-[calc(100vh-10.5rem)]">
            <RightPanel
              keyCount={apiKeyCount}
              selectedKeyTab={selectedKeyTab}
              onSelectKeyTab={setSelectedKeyTab}
              tasksByKey={tasksByKey}
              history={history}
              selectedHistoryIdByKey={selectedHistoryIdByKey}
              onSelectHistory={selectHistory}
              onRefreshHistory={refreshHistoryItem}
            />
          </div>
        </div>
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 pt-2 text-center text-[11px] text-zinc-400 sm:px-6">
        当前模型：{VIDEO_MODELS[modelKey].label}。API Key 仅保存在本浏览器 localStorage；请勿在公共电脑使用。
      </footer>
    </div>
  );
}
