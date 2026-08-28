export const STORAGE_KEYS = {
  LAST_PARAMS: 'agnes_video_last_params_v1',
  DEFAULT_PARAMS: 'agnes_video_default_params_v1',
  API_KEYS: 'agnes_video_api_keys_v1',
  KEY_COUNT: 'agnes_video_key_count_v1',
  HISTORY: 'agnes_video_history_v1',
  ACTIVE_MODEL: 'agnes_video_active_model_v1',
  PARAMS_BY_MODEL: 'agnes_video_params_by_model_v1',
  DEFAULT_PARAMS_BY_MODEL: 'agnes_video_default_params_by_model_v1',
  IMAGE_PROVIDER: 'aniflow_image_provider_v1',
  CAPCUT_IMAGE_MODEL: 'aniflow_capcut_image_model_v1',
  IMAGE_PROMPT: 'aniflow_image_prompt_v1',
};

export function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    if (parsed === null || parsed === undefined) return fallback;
    return parsed as T;
  } catch {
    return fallback;
  }
}

export function saveJSON<T>(key: string, value: T): boolean {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removeKey(key: string) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* noop */
  }
}
