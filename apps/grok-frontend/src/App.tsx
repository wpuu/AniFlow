import { useCallback, useEffect, useRef, useState } from 'react';
import KeySettings from './components/KeySettings';
import GenerateBar from './components/GenerateBar';
import SettingsForm from './components/SettingsForm';
import RightPanel from './components/RightPanel';
import CollapsibleSection from './components/CollapsibleSection';
import ImageGeneratorPanel from './components/ImageGeneratorPanel';
import { STORAGE_KEYS, loadJSON, saveJSON } from './lib/storage';
import { DEFAULT_PARAMS_BY_MODEL, VIDEO_MODELS } from './lib/constants';
import { createVideoTask, getVideoResult } from './lib/api';
import { DEFAULT_BRIDGE_URL, uploadDataUrlToBridge } from './lib/bridge';
import { genId } from './lib/imageUtils';
import { buildSafeTrialReport } from './lib/safeTrialReport';
import {
  attachVideoId,
  duplicateKeySlots,
  isValidSubmissionGuards,
  releaseAttempt,
  reserveAttempt,
  shouldReleaseVideoGuard,
} from './lib/taskSafety';
import type { SubmissionGuards } from './lib/taskSafety';
import type {
  GenerationParams,
  HistoryItem,
  TaskState,
  TaskStatus,
  VideoModelKey,
} from './lib/types';

const BUSY_STATUSES = new Set<TaskStatus>(['creating', 'queued', 'in_progress']);

function readSubmissionGuards(): SubmissionGuards | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEYS.SUBMISSION_GUARDS);
    if (!raw) return {};
    const value: unknown = JSON.parse(raw);
    return isValidSubmissionGuards(value) ? value : null;
  } catch {
    return null;
  }
}

function taskErrorMessage(error: string | { message?: string } | null | undefined): string {
  return typeof error === 'string' ? error : error?.message || '视频生成失败';
}

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

function normalizeModelKey(value: unknown): VideoModelKey {
  return value === 'v2' ? 'v2' : 'flash25';
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

function stripEphemeralImages(params: GenerationParams): GenerationParams {
  return {
    ...params,
    singleImage: params.singleImage.startsWith('data:') ? '' : params.singleImage,
    singleImageFileName: params.singleImage.startsWith('data:') ? '' : params.singleImageFileName,
    keyframeScenes: params.keyframeScenes.map((scene) =>
      scene.imageUrl.startsWith('data:')
        ? { ...scene, imageUrl: '', fileName: '' }
        : scene,
    ),
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
    normalizeModelKey(loadJSON<unknown>(STORAGE_KEYS.ACTIVE_MODEL, 'flash25')),
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
  const [submissionGuards, setSubmissionGuards] = useState<SubmissionGuards>(
    () => readSubmissionGuards() ?? {},
  );
  const [history, setHistory] = useState<HistoryItem[]>(() => loadJSON(STORAGE_KEYS.HISTORY, []));
  const [selectedKeyTab, setSelectedKeyTab] = useState(0);
  const [selectedHistoryIdByKey, setSelectedHistoryIdByKey] = useState<Record<number, string | undefined>>({});
  const [message, setMessage] = useState<{ text: string; type: 'info' | 'error' } | null>(null);

  const pollTimers = useRef<Record<number, number>>({});
  const stopFlags = useRef<Record<number, boolean>>({});
  const activeHistoryIdByKey = useRef<Record<number, string>>({});
  const mediaUploadCache = useRef<Map<string, Promise<string>>>(new Map());
  const submittingKeysRef = useRef<Set<number>>(new Set());
  const submissionGuardsRef = useRef(submissionGuards);

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
      const persisted = {
        v2: stripEphemeralImages(paramsByModel.v2),
        flash25: stripEphemeralImages(paramsByModel.flash25),
      };
      saveJSON(STORAGE_KEYS.PARAMS_BY_MODEL, persisted);
      saveJSON(STORAGE_KEYS.LAST_PARAMS, persisted.v2);
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

  // Persist the guard synchronously before the first POST. A missing/invalid
  // localStorage record must never be treated as permission to retry.
  function persistSubmissionGuards(next: SubmissionGuards): boolean {
    if (!saveJSON(STORAGE_KEYS.SUBMISSION_GUARDS, next)) {
      notify('无法持久保存视频提交安全记录，已阻止新的创建请求', 'error');
      return false;
    }
    submissionGuardsRef.current = next;
    setSubmissionGuards(next);
    return true;
  }

  function reserveVideoAttempt(
    keyIndex: number,
    attemptId: string,
    attemptModel: VideoModelKey,
  ): boolean {
    const stored = readSubmissionGuards();
    if (!stored) {
      notify('提交保护记录无法读取，请先修复本浏览器本地存储；没有创建视频', 'error');
      return false;
    }
    const next = reserveAttempt(stored, {
      keyIndex, attemptId, modelKey: attemptModel, createdAt: Date.now(), videoId: null,
    });
    if (!next) {
      setSubmissionGuards(stored);
      notify(`Key ${keyIndex + 1} 有未回收的提交记录，禁止重复创建`, 'error');
      return false;
    }
    return persistSubmissionGuards(next);
  }

  function attachVideoToGuard(keyIndex: number, attemptId: string, videoId: string) {
    const stored = readSubmissionGuards();
    if (!stored) {
      notify('已得到任务 ID，但无法读取本地安全记录；请勿重复提交', 'error');
      return false;
    }
    const next = attachVideoId(stored, keyIndex, attemptId, videoId);
    if (next === stored) return false;
    return persistSubmissionGuards(next);
  }

  function finishVideoGuard(keyIndex: number, attemptId: string) {
    const stored = readSubmissionGuards();
    if (!stored) return;
    const next = releaseAttempt(stored, keyIndex, attemptId);
    if (next !== stored) persistSubmissionGuards(next);
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

  function handleUseGeneratedImage(url: string, target: 'single' | 'first' | 'last') {
    if (target === 'single') {
      setParamsByModel((prev) => ({
        ...prev,
        [modelKey]: {
          ...prev[modelKey],
          mode: 'i2v',
          singleImage: url,
          singleImageFileName: '',
        },
      }));
      notify(`已把生图结果设为 ${VIDEO_MODELS[modelKey].label} 的单图首帧`);
      return;
    }

    const sceneIndex = target === 'first' ? 0 : 1;
    setParamsByModel((prev) => {
      const scenes = prev.flash25.keyframeScenes.map((scene) => ({ ...scene }));
      while (scenes.length < 2) {
        scenes.push({ id: genId('flash-frame'), imageUrl: '', fileName: '' });
      }
      scenes[sceneIndex] = { ...scenes[sceneIndex], imageUrl: url, fileName: '' };
      return {
        ...prev,
        flash25: {
          ...prev.flash25,
          mode: 'keyframes',
          keyframeScenes: scenes,
        },
      };
    });
    setModelKey('flash25');
    notify(`已设为 Agnes Video 2.5 Flash ${target === 'first' ? '首帧' : '尾帧'}`);
  }

  function handleKeyCountChange(count: number) {
    const hiddenBusyKey = Object.entries(tasksByKey).some(
      ([index, task]) => Number(index) >= count && BUSY_STATUSES.has(task.status),
    ) || Object.keys(submissionGuards).some((index) => Number(index) >= count);
    if (hiddenBusyKey) {
      notify('不能隐藏正在运行或有未回收任务的 Key；请先核实对应任务', 'error');
      return;
    }
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

  function uploadLocalImage(dataUrl: string): Promise<string> {
    const cached = mediaUploadCache.current.get(dataUrl);
    if (cached) return cached;

    const upload = uploadDataUrlToBridge(dataUrl, DEFAULT_BRIDGE_URL)
      .then((result) => result.url)
      .catch((error) => {
        mediaUploadCache.current.delete(dataUrl);
        throw error;
      });
    mediaUploadCache.current.set(dataUrl, upload);
    return upload;
  }

  async function prepareFlashParams(source: GenerationParams): Promise<GenerationParams> {
    const next: GenerationParams = {
      ...source,
      keyframeScenes: source.keyframeScenes.map((scene) => ({ ...scene })),
    };

    async function resolveImage(value: string): Promise<string> {
      const trimmed = value.trim();
      if (isPublicImageUrl(trimmed)) return trimmed;
      if (trimmed.startsWith('data:image/')) {
        notify('正在通过 AniFlow 本机 Bridge 上传本地图片…');
        return uploadLocalImage(trimmed);
      }
      throw new Error('2.5 Flash 的参考帧必须是本地上传图片或可公开访问的 http(s) 图片 URL');
    }

    if (next.mode === 'i2v' || next.mode === 'reference') {
      if (!next.singleImage) throw new Error(
        next.mode === 'reference' ? '参考图模式需要一张公开可访问图片' : '图生视频模式需要首帧图片',
      );
      next.singleImage = await resolveImage(next.singleImage);
      next.singleImageFileName = undefined;
      return next;
    }

    if (next.mode === 'keyframes') {
      const indexes = next.keyframeScenes
        .map((scene, index) => (scene.imageUrl.trim() ? index : -1))
        .filter((index) => index >= 0);
      if (indexes.length < 2) throw new Error('2.5 Flash 首尾帧模式需要首帧和尾帧两张图片');

      const firstIndex = indexes[0];
      const lastIndex = indexes[1];
      const [firstUrl, lastUrl] = await Promise.all([
        resolveImage(next.keyframeScenes[firstIndex].imageUrl),
        resolveImage(next.keyframeScenes[lastIndex].imageUrl),
      ]);
      next.keyframeScenes[firstIndex] = {
        ...next.keyframeScenes[firstIndex],
        imageUrl: firstUrl,
        fileName: undefined,
      };
      next.keyframeScenes[lastIndex] = {
        ...next.keyframeScenes[lastIndex],
        imageUrl: lastUrl,
        fileName: undefined,
      };
    }

    return next;
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
            patch.videoUrl = result.url || result.metadata?.url || null;
            patch.progress = 100;
            if (!shouldReleaseVideoGuard(status, patch.videoUrl)) {
              patch.status = 'submission_unknown';
              patch.error = '任务完成但无有效 MP4 地址：已保留安全锁，可继续查询原视频';
            }
          }
          if (status === 'failed') {
            patch.error = taskErrorMessage(result.error);
          }
          updateTaskState(keyIndex, patch);
          const terminal = shouldReleaseVideoGuard(status, patch.videoUrl);
          updateHistoryItem(historyId, {
            ...patch,
            ...(terminal ? { finishedAt: Date.now() } : {}),
          } as Partial<HistoryItem>);

          if (status === 'completed' || status === 'failed') {
            if (shouldReleaseVideoGuard(status, patch.videoUrl)) finishVideoGuard(keyIndex, historyId);
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
            const warning = `状态查询中断（${msg}）。原任务可能仍在服务器运行，请仅恢复查询，勿重新创建。`;
            updateTaskState(keyIndex, { status: 'stopped', error: warning, modelKey: taskModelKey });
            updateHistoryItem(historyId, { status: 'stopped', error: warning });
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
      // A double click must not create two requests before React re-renders.
      if (submittingKeysRef.current.has(keyIndex)) return;

      const storedGuards = readSubmissionGuards();
      if (!storedGuards) {
        notify('本地提交保护记录读取失败，禁止发送视频请求', 'error');
        return;
      }
      if (storedGuards[String(keyIndex)]) {
        setSubmissionGuards(storedGuards);
        notify(`Key ${keyIndex + 1} 的原请求尚未核实。请先恢复查询或人工确认后解锁`, 'error');
        return;
      }
      if (BUSY_STATUSES.has(tasksByKey[keyIndex]?.status ?? 'idle')) {
        notify(`Key ${keyIndex + 1} 正在生成，请勿重复创建`, 'error');
        return;
      }

      const apiKey = apiKeys[keyIndex]?.trim();
      if (!apiKey) {
        notify(`请先填写 Key ${keyIndex + 1}`, 'error');
        return;
      }
      // The same secret configured in two slots must not create concurrent tasks.
      const duplicateActive = apiKeys.some((other, index) => (
        index !== keyIndex
        && other?.trim() === apiKey
        && (submittingKeysRef.current.has(index) || Boolean(storedGuards[String(index)]))
      ));
      if (duplicateActive) {
        notify('同一 Agnes Key 在其他槽位已有未结束任务：已阻止重复提交', 'error');
        return;
      }
      if (!params.prompt.trim()) {
        notify('请先填写提示词', 'error');
        return;
      }
      if ((params.mode === 'i2v' || params.mode === 'reference') && !params.singleImage) {
        notify('当前视频模式需要一张公开可访问图片，请先填入图片URL', 'error');
        return;
      }

      submittingKeysRef.current.add(keyIndex);
      try {
        let requestParams = params;
        if (modelKey === 'flash25') {
          try {
            requestParams = await prepareFlashParams(params);
          } catch (err) {
            notify(err instanceof Error ? err.message : '本地图片准备失败；没有创建视频', 'error');
            return;
          }
        } else if (params.mode === 'keyframes') {
          const valid = params.keyframeScenes.filter((scene) => scene.imageUrl.trim());
          if (valid.length < 2) {
            notify('V2.0 多关键帧模式至少需要两张图片；没有创建视频', 'error');
            return;
          }
        }

        const historyId = genId('task');
        // Fail closed if localStorage is denied/full. Reservation happens BEFORE the video POST.
        if (!reserveVideoAttempt(keyIndex, historyId, modelKey)) return;

        stopFlags.current[keyIndex] = false;
        activeHistoryIdByKey.current[keyIndex] = historyId;
        setSelectedKeyTab(keyIndex);

        const modelName = VIDEO_MODELS[modelKey].apiModel;
        const newItem: HistoryItem = {
          id: historyId,
          keyIndex,
          createdAt: Date.now(),
          promptPreview: requestParams.prompt.trim().slice(0, 100),
          modelKey,
          modelName,
          mode: requestParams.mode,
          ratio: requestParams.ratio,
          resolution: requestParams.resolution,
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
          const created = await createVideoTask(apiKey, modelKey, requestParams);
          // Agnes GET needs video_id, NOT its potentially different task_id.
          const videoId = typeof created.video_id === 'string' ? created.video_id.trim() : '';
          if (!videoId) {
            throw new Error('创建请求返回成功但没有 video_id；可能已提交，请先查服务商任务历史');
          }
          const taskId = created.task_id || created.id || '';
          if (!attachVideoToGuard(keyIndex, historyId, videoId)) {
            notify('已获得 video_id，但保护账本写回失败；不要重试创建', 'error');
          }
          const status = mapStatus(created.status);
          updateTaskState(keyIndex, { status, progress: created.progress ?? 0, videoId, taskId, modelKey });
          updateHistoryItem(historyId, { status, progress: created.progress ?? 0, videoId, taskId });
          poll(keyIndex, apiKey, videoId, historyId, modelKey);
        } catch (err) {
          const reason = err instanceof Error ? err.message : '创建响应不确定';
          const warning = `${reason}。该请求可能已被服务端接受；请核实原任务，不要重新点击生成。`;
          updateTaskState(keyIndex, { status: 'submission_unknown', error: warning, modelKey });
          updateHistoryItem(historyId, { status: 'submission_unknown', error: warning });
          delete activeHistoryIdByKey.current[keyIndex];
          notify(`Key ${keyIndex + 1} 提交结果待核实；已保留本地安全锁`, 'error');
        }
      } finally {
        submittingKeysRef.current.delete(keyIndex);
      }
    },
    [apiKeys, modelKey, params, poll, tasksByKey],
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
    if (duplicateKeySlots(apiKeys.slice(0, apiKeyCount)).length) {
      notify('检测到重复 Agnes API Key；请保留每条 Key 一个槽位。本次未发送任何生成请求', 'error');
      return;
    }
    const eligible = Array.from({ length: apiKeyCount }, (_, index) => index)
      .filter((index) => (
        !!apiKeys[index]?.trim()
        && !BUSY_STATUSES.has(tasksByKey[index]?.status ?? 'idle')
        && !submissionGuards[String(index)]
        && !submittingKeysRef.current.has(index)
      ));
    if (!eligible.length) {
      notify('没有可用 Key：请先核实原任务或检查密钥配置', 'error');
      return;
    }
    if (!window.confirm(
      `将使用 ${eligible.length} 条 Key，向 Agnes 分别提交 1 个视频生成任务（共 ${eligible.length} 次创建请求）。`
      + '这是真实生成，不是健康检查；可能消耗额度或费用。是否确认发送？',
    )) return;
    eligible.forEach((index) => { void startGeneration(index); });
  }

  function resumeExistingGuard(keyIndex: number) {
    const guard = readSubmissionGuards()?.[String(keyIndex)];
    if (!guard?.videoId) {
      notify('没有可查询的 video_id；先在 Agnes 账号历史确认是否创建任务', 'error');
      return;
    }
    const apiKey = apiKeys[keyIndex]?.trim();
    if (!apiKey) {
      notify(`请先在 Key ${keyIndex + 1} 输入原账号的合法密钥`, 'error');
      return;
    }
    if (BUSY_STATUSES.has(tasksByKey[keyIndex]?.status ?? 'idle')) {
      notify('已经在轮询原任务，无需重复恢复');
      return;
    }
    stopFlags.current[keyIndex] = false;
    activeHistoryIdByKey.current[keyIndex] = guard.attemptId;
    updateTaskState(keyIndex, { status: 'queued', videoId: guard.videoId, modelKey: guard.modelKey, error: null });
    setHistory((prev) => {
      if (prev.some((entry) => entry.id === guard.attemptId)) {
        return prev.map((entry) => (
          entry.id === guard.attemptId ? { ...entry, status: 'queued', error: null } : entry
        ));
      }
      // Restore the original task identity, not invented prompt/mode details.
      const recovered: HistoryItem = {
        id: guard.attemptId,
        keyIndex,
        createdAt: guard.createdAt,
        promptPreview: '从安全账本恢复；原始提示词与模式已无法核实',
        modelKey: guard.modelKey,
        modelName: VIDEO_MODELS[guard.modelKey].apiModel,
        mode: 'unknown',
        ratio: 'unknown',
        resolution: 'unknown',
        status: 'queued',
        progress: 0,
        videoUrl: null,
        videoId: guard.videoId,
        taskId: null,
        error: null,
      };
      return [recovered, ...prev];
    });
    poll(keyIndex, apiKey, guard.videoId, guard.attemptId, guard.modelKey);
  }

  function confirmUnlockGuard(keyIndex: number) {
    const guard = readSubmissionGuards()?.[String(keyIndex)];
    if (!guard) return;
    const confirmed = window.confirm(
      `Key ${keyIndex + 1} 的视频提交记录仍未结案。只有在 Agnes 平台已核实没有正在运行/未回收的原任务`
      + '（或确认原任务已完成并已保存结果）之后，才允许解除安全锁。解除后再次生成可能产生第二条任务和费用。确认已经核实？',
    );
    if (!confirmed) return;
    finishVideoGuard(keyIndex, guard.attemptId);
    updateTaskState(keyIndex, { status: 'stopped', error: '已由操作员确认并手动解除安全锁' });
    updateHistoryItem(guard.attemptId, { status: 'stopped', error: '操作员手动核实并解除提交安全锁' });
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
        if (status === 'completed') {
          patch.videoUrl = result.url || result.metadata?.url || null;
          if (!shouldReleaseVideoGuard(status, patch.videoUrl)) {
            patch.status = 'submission_unknown';
            patch.error = '任务完成但无有效 MP4 地址，已保留防重锁；请继续查原任务';
          } else {
            patch.error = null;
          }
        }
        if (status === 'failed') patch.error = taskErrorMessage(result.error);
        if (shouldReleaseVideoGuard(status, patch.videoUrl)) {
          finishVideoGuard(item.keyIndex, item.id);
        }
        updateHistoryItem(item.id, {
          ...patch,
          ...(shouldReleaseVideoGuard(status, patch.videoUrl)
            ? { finishedAt: item.finishedAt ?? Date.now() } : {}),
        });

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
    const safeParams = stripEphemeralImages(params);
    const next = { ...defaults, [modelKey]: safeParams };
    saveJSON(STORAGE_KEYS.DEFAULT_PARAMS_BY_MODEL, next);
    if (modelKey === 'v2') saveJSON(STORAGE_KEYS.DEFAULT_PARAMS, safeParams);
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

  function handleCopySafeReport() {
    const report = buildSafeTrialReport(
      apiKeys.slice(0, apiKeyCount).map((k) => Boolean(k?.trim())),
      history,
      Object.keys(submissionGuards).map(Number),
      Date.now(),
    );
    if (!navigator.clipboard?.writeText) {
      notify('当前浏览器不支持自动复制：请在可信桌面浏览器打开 AniFlow', 'error');
      return;
    }
    void navigator.clipboard.writeText(report)
      .then(() => notify('已复制9-Key安全摘要：不含任何 Key、提示词、视频 URL 或任务 ID'))
      .catch(() => notify('复制未成功，请检查浏览器剪贴板权限', 'error'));
  }

  function handleClearHistory() {
    const anyBusy = Object.values(tasksByKey).some((task) => BUSY_STATUSES.has(task.status))
      || Object.keys(submissionGuards).length > 0;
    if (anyBusy) {
      notify('仍有运行中或未核实的原任务；暂不能清空历史', 'error');
      return;
    }
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
                  AniFlow 动画工厂
                </h1>
                <p className="text-xs text-zinc-400">
                  当前视频：{VIDEO_MODELS[modelKey].label} · 多 Key 并行 · 生图 Provider 可切换
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
                onClick={handleCopySafeReport}
                className="rounded-md border border-indigo-300 px-2.5 py-1.5 font-medium text-indigo-600 hover:bg-indigo-50"
                title="复制不含 API Key、任务 ID、签名视频 URL、原始错误或提示词的测试摘要"
              >
                复制9-Key安全测试摘要
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
              guardedKeyIndexes={new Set(Object.keys(submissionGuards).map(Number))}
              onGenerate={startGeneration}
              onStop={stopGeneration}
              onGenerateAll={generateAll}
            />
          </div>

          {Object.keys(submissionGuards).length > 0 ? (
            <div className="mt-3 space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="font-semibold">视频提交安全记录：这些 Key 在确认原任务状态前禁止重新提交。</p>
              <p>刷新页面、停止跟踪、网络中断均不意味着服务器取消生成。继续查询只发送 GET，不创建视频。</p>
              <div className="flex flex-wrap gap-2">
                {Object.values(submissionGuards)
                  .sort((a, b) => a.keyIndex - b.keyIndex)
                  .map((guard) => (
                    <div key={guard.attemptId} className="flex items-center gap-2 rounded bg-white px-2 py-1">
                      <strong>Key {guard.keyIndex + 1}</strong>
                      <span>{guard.videoId ? '有原视频 ID' : '提交结果不明'}</span>
                      {guard.videoId ? (
                        <button type="button" onClick={() => resumeExistingGuard(guard.keyIndex)}
                          className="rounded border border-amber-500 px-2 py-1 hover:bg-amber-100">
                          继续查原任务
                        </button>
                      ) : null}
                      <button type="button" onClick={() => confirmUnlockGuard(guard.keyIndex)}
                        className="rounded border border-amber-500 px-2 py-1 hover:bg-amber-100">
                        人工核实后解锁
                      </button>
                    </div>
                  ))}
              </div>
            </div>
          ) : null}

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
              busyKeyIndexes={new Set([
                ...Object.entries(tasksByKey)
                  .filter(([, task]) => BUSY_STATUSES.has(task.status))
                  .map(([index]) => Number(index)),
                ...Object.keys(submissionGuards).map(Number),
              ])}
              onKeyCountChange={handleKeyCountChange}
              onKeyChange={handleKeyChange}
            />
          </CollapsibleSection>

          <CollapsibleSection
            title="AI 生图 / 参考图"
            subtitle="Agnes Image 与 CapCut / Seedream 可切换，结果可直接送入视频首尾帧"
          >
            <ImageGeneratorPanel
              apiKeys={apiKeys.slice(0, apiKeyCount)}
              onUseResult={handleUseGeneratedImage}
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
        当前视频模型：{VIDEO_MODELS[modelKey].label}。API Key 仅保存在本浏览器 localStorage；2.5 Flash 本地图片会自动经 {DEFAULT_BRIDGE_URL} 上传为公网 URL。
      </footer>
    </div>
  );
}
