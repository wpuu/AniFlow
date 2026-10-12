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
import { getBridgeVersion } from './lib/bridge';
import type { BridgeVersion } from './lib/bridge';
import { genId } from './lib/imageUtils';
import { rememberPrompt } from './lib/promptHistory';
import type { SavedPrompt } from './lib/promptHistory';
import { buildSafeTrialReport } from './lib/safeTrialReport';
import {
  attachVideoId,
  duplicateKeySlots,
  isValidSubmissionGuards,
  releaseAttempt,
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
  // Migrate old v2 selection to the official free Flash variant.
  return value === 'paid25' ? 'paid25' : 'flash25';
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
      paid25: mergeParams(DEFAULT_PARAMS_BY_MODEL.paid25, saved.paid25),
    };
  });

  const params = paramsByModel[modelKey];

  const [tasksByKey, setTasksByKey] = useState<Record<number, TaskState>>({});
  const [submissionGuards, setSubmissionGuards] = useState<SubmissionGuards>(
    () => readSubmissionGuards() ?? {},
  );
  const [history, setHistory] = useState<HistoryItem[]>(() => loadJSON(STORAGE_KEYS.HISTORY, []));
  const [promptHistory, setPromptHistory] = useState<SavedPrompt[]>(
    () => loadJSON<SavedPrompt[]>(STORAGE_KEYS.PROMPT_HISTORY, []),
  );
  const [selectedKeyTab, setSelectedKeyTab] = useState(0);
  const [selectedHistoryIdByKey, setSelectedHistoryIdByKey] = useState<Record<number, string | undefined>>({});
  const [message, setMessage] = useState<{ text: string; type: 'info' | 'error' } | null>(null);
  const [runningBuild, setRunningBuild] = useState<BridgeVersion | null>(null);

  const pollTimers = useRef<Record<number, number>>({});
  const stopFlags = useRef<Record<number, boolean>>({});
  const activeHistoryIdByKey = useRef<Record<number, string>>({});
  const submittingKeysRef = useRef<Set<number>>(new Set());
  const submissionGuardsRef = useRef(submissionGuards);

  useEffect(() => {
    saveJSON(STORAGE_KEYS.API_KEYS, apiKeys);
  }, [apiKeys]);

  useEffect(() => {
    // Display the actual localhost build. Never infer "latest" from a PR title.
    void getBridgeVersion()
      .then(setRunningBuild)
      .catch(() => setRunningBuild(null));
  }, []);

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
    saveJSON(STORAGE_KEYS.PROMPT_HISTORY, promptHistory.slice(0, 40));
  }, [promptHistory]);

  useEffect(() => {
    // Save every committed edit without waiting: a fast submit -> timeout ->
    // page reload must not lose its prompt and turn retry into a no-op.
    const persisted = {
      v2: stripEphemeralImages(paramsByModel.v2),
      flash25: stripEphemeralImages(paramsByModel.flash25),
      paid25: stripEphemeralImages(paramsByModel.paid25),
    };
    saveJSON(STORAGE_KEYS.PARAMS_BY_MODEL, persisted);
    saveJSON(STORAGE_KEYS.LAST_PARAMS, persisted.v2);
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

  // A previous timeout is history, never a permanent ban on the owner's next click.
  function persistSubmissionGuards(next: SubmissionGuards): void {
    submissionGuardsRef.current = next;
    setSubmissionGuards(next);
    saveJSON(STORAGE_KEYS.SUBMISSION_GUARDS, next);
  }

  function reserveVideoAttempt(keyIndex: number, attemptId: string, attemptModel: VideoModelKey): void {
    const old = readSubmissionGuards() ?? {};
    const previous = old[String(keyIndex)];
    if (previous?.videoId) {
      setHistory((prev) => {
        if (prev.some((item) => item.id === previous.attemptId)) return prev;
        return [{
          id: previous.attemptId, keyIndex, createdAt: previous.createdAt,
          promptPreview: '已知视频编号的历史任务（原提示词未知）',
          modelKey: previous.modelKey, modelName: VIDEO_MODELS[previous.modelKey].apiModel,
          mode: 'unknown', ratio: 'unknown', resolution: 'unknown',
          status: 'stopped', progress: 0, videoUrl: null,
          videoId: previous.videoId, taskId: null,
          error: '这条历史任务可通过历史记录中的刷新状态查询',
        }, ...prev];
      });
    }
    persistSubmissionGuards({
      ...old,
      [String(keyIndex)]: {
        keyIndex, attemptId, modelKey: attemptModel, createdAt: Date.now(), videoId: null,
      },
    });
  }

  function attachVideoToGuard(keyIndex: number, attemptId: string, videoId: string) {
    const stored = readSubmissionGuards();
    if (!stored) {
      notify('已得到任务 ID，但无法读取本地安全记录；请勿重复提交', 'error');
      return false;
    }
    const next = attachVideoId(stored, keyIndex, attemptId, videoId);
    if (next === stored) return false;
    persistSubmissionGuards(next);
    return true;
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
    );
    if (hiddenBusyKey) {
      notify('请先停止所隐藏 Key 的当前任务跟踪', 'error');
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

  async function prepareFlashParams(source: GenerationParams): Promise<GenerationParams> {
    const next: GenerationParams = {
      ...source,
      keyframeScenes: source.keyframeScenes.map((scene) => ({ ...scene })),
    };

    async function resolveImage(value: string): Promise<string> {
      const trimmed = value.trim();
      if (isPublicImageUrl(trimmed)) return trimmed;
      if (/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/i.test(trimmed)) {
        // Agnes' public specification prefers URLs; other integration examples
        // accept Base64. Forward once as an experimental direct input, without
        // uploading the owner's image to a third-party S3/R2 bucket.
        if (trimmed.length > 5_500_000) {
          throw new Error('图片过大（超过约4MB）。请压缩图片后重试，或填写公共HTTPS链接。');
        }
        return trimmed;
      }
      throw new Error('图片需为PNG/JPEG/WebP本地文件，或可公开访问的HTTPS图片链接。');
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
              patch.status = 'stopped';
              patch.error = 'Agnes 报告任务完成但没有视频链接；可以从历史记录重新查询。';
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
            const warning = `状态查询中断：${msg}。已有的 video_id 保存在历史中，可刷新；也可以重新点击生成新任务。`;
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
    async (keyIndex: number, paidConfirmed = false) => {
      if (modelKey === 'paid25' && !paidConfirmed) {
        const perSecond = params.resolution === '1080p' ? 0.040 : 0.025;
        const estimated = (perSecond * params.seconds).toFixed(3);
        if (!window.confirm(
          `你选择了付费 Agnes Video 2.5（${params.resolution}），单条${params.seconds}秒官方标价约 ${estimated}。`
          + '实际按账户结算，确认创建这一条视频任务吗？',
        )) return;
      }
      // A double click must not create two requests before React re-renders.
      if (submittingKeysRef.current.has(keyIndex)) return;

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
        index !== keyIndex && other?.trim() === apiKey && submittingKeysRef.current.has(index)
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
        if (modelKey !== 'v2') {
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
        // One explicit click = one POST; old localStorage records never stop a new attempt.
        reserveVideoAttempt(keyIndex, historyId, modelKey);
        setPromptHistory((prev) => rememberPrompt(prev, requestParams.prompt, modelKey, Date.now()));

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
          const knownFailure = /^HTTP (400|401|403|404|409|422|429|503)\b/.test(reason);
          const status: TaskStatus = knownFailure ? 'failed' : 'submission_unknown';
          const explanation = knownFailure
            ? `提交失败：${reason}。可以再次点击生成。`
            : `没有收到 Agnes 的任务编号：${reason}。可以直接再点击生成；如果上次实际已接收，可能出现重复任务。`;
          finishVideoGuard(keyIndex, historyId);
          updateTaskState(keyIndex, { status, error: explanation, modelKey });
          updateHistoryItem(historyId, { status, error: explanation, finishedAt: Date.now() });
          delete activeHistoryIdByKey.current[keyIndex];
          notify(`Key ${keyIndex + 1}：${explanation}`, 'error');
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
        && !submittingKeysRef.current.has(index)
      ));
    if (!eligible.length) {
      notify('没有可用 Key：请先核实原任务或检查密钥配置', 'error');
      return;
    }
    // One click on the free Flash model is the user's explicit batch action.
    // Do not make a free 9-Key test navigate an irrelevant billing dialogue.
    if (modelKey === 'paid25') {
      const estimated = ((params.resolution === '1080p' ? 0.040 : 0.025)
        * params.seconds * eligible.length).toFixed(3);
      if (!window.confirm(
        `当前是付费 Agnes Video 2.5，${eligible.length} 条视频官方预估约 ${estimated}。确认提交？`,
      )) return;
    }
    eligible.forEach((index) => { void startGeneration(index, true); });
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
            patch.status = 'stopped';
            patch.error = 'Agnes 已报告完成，但未返回可播放地址；可点击历史记录里的刷新状态再次查询。';
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
    // Old V2.0 settings are retained only for viewing history, never for new submissions.
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
      Object.entries(submissionGuards).filter(([, guard]) => Boolean(guard.videoId))
        .map(([index]) => Number(index)),
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
    const anyBusy = Object.values(tasksByKey).some((task) => BUSY_STATUSES.has(task.status));
    if (anyBusy) {
      notify('正在生成的任务尚未停止跟踪', 'error');
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
              busyKeyIndexes={new Set([
                ...Object.entries(tasksByKey)
                  .filter(([, task]) => BUSY_STATUSES.has(task.status))
                  .map(([index]) => Number(index)),
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
            promptHistory={promptHistory}
            onSavePrompt={() => {
              setPromptHistory((prev) => rememberPrompt(prev, params.prompt, modelKey, Date.now()));
              notify('当前提示词已保存，可从历史列表切换');
            }}
            onLoadPrompt={(value) => updateParams((prev) => ({ ...prev, prompt: value }))}
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
        <span className="font-semibold">
          正在运行版本：{runningBuild?.source_commit?.slice(0, 12)
            ?? (runningBuild?.build_type === 'source' ? '本地源码版' : '未验证')}
          {runningBuild?.build_type === 'prebuilt' && !runningBuild.frontend_verified
            ? ' · 校验失败，请重装完整版' : ''}
        </span>
        <span className="mx-2">·</span>
        当前视频模型：{VIDEO_MODELS[modelKey].label}。服务重启不会删除浏览器保存的 Key 和历史。
      </footer>
    </div>
  );
}
