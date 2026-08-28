import { useCallback, useEffect, useRef, useState } from 'react';
import KeySettings from './components/KeySettings';
import GenerateBar from './components/GenerateBar';
import SettingsForm from './components/SettingsForm';
import RightPanel from './components/RightPanel';
import CollapsibleSection from './components/CollapsibleSection';
import { STORAGE_KEYS, loadJSON, saveJSON } from './lib/storage';
import { DEFAULT_PARAMS } from './lib/constants';
import { createVideoTask, getVideoResult } from './lib/api';
import { genId } from './lib/imageUtils';
import type { GenerationParams, HistoryItem, TaskState, TaskStatus } from './lib/types';

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

export default function App() {
  const [apiKeyCount, setApiKeyCount] = useState<number>(() => loadJSON(STORAGE_KEYS.KEY_COUNT, 1));
  const [apiKeys, setApiKeys] = useState<string[]>(() => {
    const saved = loadJSON<string[]>(STORAGE_KEYS.API_KEYS, []);
    const count = loadJSON(STORAGE_KEYS.KEY_COUNT, 1);
    return Array.from({ length: count }, (_, i) => saved[i] ?? '');
  });

  const [params, setParams] = useState<GenerationParams>(() => loadJSON(STORAGE_KEYS.LAST_PARAMS, DEFAULT_PARAMS));

  const [tasksByKey, setTasksByKey] = useState<Record<number, TaskState>>({});
  const [history, setHistory] = useState<HistoryItem[]>(() => loadJSON(STORAGE_KEYS.HISTORY, []));
  const [selectedKeyTab, setSelectedKeyTab] = useState(0);
  const [selectedHistoryIdByKey, setSelectedHistoryIdByKey] = useState<Record<number, string | undefined>>({});
  const [message, setMessage] = useState<{ text: string; type: 'info' | 'error' } | null>(null);

  const pollTimers = useRef<Record<number, number>>({});
  const stopFlags = useRef<Record<number, boolean>>({});

  useEffect(() => {
    saveJSON(STORAGE_KEYS.API_KEYS, apiKeys);
  }, [apiKeys]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.KEY_COUNT, apiKeyCount);
  }, [apiKeyCount]);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.HISTORY, history.slice(0, 300));
  }, [history]);

  useEffect(() => {
    const t = window.setTimeout(() => saveJSON(STORAGE_KEYS.LAST_PARAMS, params), 500);
    return () => window.clearTimeout(t);
  }, [params]);

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
    (keyIndex: number, apiKey: string, videoId: string, historyId: string, retriesLeft = 5) => {
      const run = async () => {
        if (stopFlags.current[keyIndex]) return;
        try {
          const result = await getVideoResult(apiKey, videoId);
          if (stopFlags.current[keyIndex]) return;
          const status = mapStatus(result.status);
          const patch: Partial<TaskState> = {
            status,
            progress: result.progress ?? 0,
            size: result.size,
            seconds: result.seconds,
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
            return;
          }
          pollTimers.current[keyIndex] = window.setTimeout(
            () => poll(keyIndex, apiKey, videoId, historyId, 5),
            3000,
          );
        } catch (err) {
          if (stopFlags.current[keyIndex]) return;
          if (retriesLeft > 0) {
            pollTimers.current[keyIndex] = window.setTimeout(
              () => poll(keyIndex, apiKey, videoId, historyId, retriesLeft - 1),
              4000,
            );
          } else {
            const msg = err instanceof Error ? err.message : '网络异常，查询进度失败';
            updateTaskState(keyIndex, { status: 'failed', error: msg });
            updateHistoryItem(historyId, { status: 'failed', error: msg });
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
      if (params.mode === 'keyframes') {
        const valid = params.keyframeScenes.filter((s) => s.imageUrl.trim());
        if (valid.length < 2) {
          notify('多关键帧模式至少需要上传 2 张关键帧图片', 'error');
          return;
        }
      }

      saveJSON(STORAGE_KEYS.LAST_PARAMS, params);
      stopFlags.current[keyIndex] = false;

      const historyId = genId('task');
      setSelectedKeyTab(keyIndex);

      const newItem: HistoryItem = {
        id: historyId,
        keyIndex,
        createdAt: Date.now(),
        promptPreview: params.prompt.trim().slice(0, 100),
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
      });

      try {
        const created = await createVideoTask(apiKey, params);
        const videoId = created.video_id || created.id || created.task_id || '';
        const taskId = created.task_id || created.id || '';
        if (!videoId) throw new Error('未获取到有效的视频任务 ID，请检查返回结果');
        const status = mapStatus(created.status);
        updateTaskState(keyIndex, { status, progress: created.progress ?? 0, videoId, taskId });
        updateHistoryItem(historyId, { status, progress: created.progress ?? 0, videoId, taskId });
        poll(keyIndex, apiKey, videoId, historyId);
      } catch (err) {
        const msg = err instanceof Error ? err.message : '创建任务失败';
        updateTaskState(keyIndex, { status: 'failed', error: msg });
        updateHistoryItem(historyId, { status: 'failed', error: msg });
        notify(msg, 'error');
      }
    },
    [apiKeys, params, poll],
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
    const id = selectedHistoryIdByKey[keyIndex];
    if (id) {
      setHistory((prev) =>
        prev.map((h) =>
          h.id === id && h.status !== 'completed' && h.status !== 'failed' ? { ...h, status: 'stopped' } : h,
        ),
      );
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
    getVideoResult(apiKey, item.videoId)
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
        updateTaskState(item.keyIndex, patch as Partial<TaskState>);
      })
      .catch((err) => notify(err instanceof Error ? err.message : '刷新失败', 'error'));
  }

  function selectHistory(keyIndex: number, id: string) {
    setSelectedHistoryIdByKey((prev) => ({ ...prev, [keyIndex]: id }));
  }

  function handleSaveAsDefault() {
    saveJSON(STORAGE_KEYS.DEFAULT_PARAMS, params);
    notify('已将当前设置保存为默认设置');
  }

  function handleRestoreDefault() {
    const def = loadJSON<GenerationParams | null>(STORAGE_KEYS.DEFAULT_PARAMS, null);
    if (def) {
      setParams(def);
      notify('已恢复为默认设置');
    } else {
      notify('尚未保存过默认设置', 'error');
    }
  }

  function handleRestoreLast() {
    const last = loadJSON<GenerationParams | null>(STORAGE_KEYS.LAST_PARAMS, null);
    if (last) {
      setParams(last);
      notify('已恢复上一次的内容');
    } else {
      notify('暂无上一次的记录', 'error');
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
                  Agnes Video V2.0 视频生成工作台
                </h1>
                <p className="text-xs text-zinc-400">文生视频 · 图生视频 · 多关键帧动画 · 多 Key 并行生成</p>
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

          <SettingsForm params={params} onChange={setParams} />
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
        本工具直接调用 Agnes Video V2.0 官方接口（apihub.agnes-ai.com），请妥善保管你的 API Key。
      </footer>
    </div>
  );
}
