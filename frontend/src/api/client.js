function resolveApiBase() {
  const explicit = (
    import.meta.env.VITE_API_URL ||
    import.meta.env.VITE_API_BASE_URL ||
    ''
  )
    .trim()
    .replace(/\/+$/, '');
  if (explicit) {
    return explicit;
  }
  const isProductionHost =
    typeof window !== 'undefined' &&
    /(^|\.)aishorts\.space$/i.test(window.location.hostname);
  if (isProductionHost || import.meta.env.PROD) {
    return '';
  }
  return 'http://127.0.0.1:8000';
}

export const API_BASE = resolveApiBase();

export const AUTH_TOKEN_KEY = 'ai_shorts_auth_token';

let unauthorizedHandler = null;

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = typeof handler === 'function' ? handler : null;
}

export function getAuthToken() {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setAuthToken(token) {
  try {
    if (token) {
      window.localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    // Ignore storage unavailability cleanly
  }
}

export function clearAuthToken() {
  setAuthToken('');
}

async function requestJson(path, options = {}) {
  const { skipAuth = false, headers: customHeaders = {}, ...fetchOptions } = options;
  const headers = new Headers(customHeaders);
  if (!skipAuth) {
    const token = getAuthToken();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (response.status === 401 && !skipAuth) {
    clearAuthToken();
    if (unauthorizedHandler) {
      unauthorizedHandler();
    }
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const rawMessage =
      (data && (data.detail || data.message)) ||
      `Request failed with HTTP ${response.status}`;
    const formattedMessage =
      response.status === 429
        ? 'Too many requests (HTTP 429) — automatic refresh paused. Please wait a moment and click Refresh.'
        : typeof rawMessage === 'string'
        ? rawMessage
        : JSON.stringify(rawMessage);
    const err = new Error(formattedMessage);
    err.status = response.status;
    throw err;
  }
  return data;
}

export function registerUser({ email, password, displayName }) {
  return requestJson('/api/auth/register', {
    method: 'POST',
    skipAuth: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      display_name: displayName || undefined,
    }),
  });
}

export function loginUser({ email, password }) {
  return requestJson('/api/auth/login', {
    method: 'POST',
    skipAuth: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
}

export function getCurrentUser() {
  return requestJson('/api/auth/me');
}

export function getHealth() {
  return requestJson('/api/health', { skipAuth: true });
}

export function listCelebrities() {
  return requestJson('/api/celebrities');
}

export function createCelebrity({ name, category, aliases }) {
  return requestJson('/api/celebrities', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, category, aliases }),
  });
}

export function listClips(celebrityId) {
  const query = celebrityId ? `?celebrity_id=${encodeURIComponent(celebrityId)}` : '';
  return requestJson(`/api/clips${query}`);
}

export function uploadLocalClips({ celebrityId, files, tags }) {
  const form = new FormData();
  form.append('celebrity_id', celebrityId);
  form.append('tags', tags || '');
  Array.from(files).forEach((file) => {
    form.append('files', file);
  });
  return requestJson('/api/clips/upload-local', {
    method: 'POST',
    body: form,
  });
}

export function listProjects() {
  return requestJson('/api/projects');
}

export function createProject(payload) {
  return requestJson('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getProjectVideoUrl(projectId) {
  const baseUrl = `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/video`;
  const token = getAuthToken();
  return token ? `${baseUrl}?token=${encodeURIComponent(token)}` : baseUrl;
}

export function startLocalFolderScan({ folderPath, category }) {
  return requestJson('/api/clips/scan-local-folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder_path: folderPath,
      category: category || 'NBA',
    }),
  });
}

export function getLocalFolderScanStatus(scanId) {
  return requestJson(`/api/clips/scan-local-folder/${encodeURIComponent(scanId)}`);
}

export function deleteProject(projectId) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: 'DELETE',
  });
}
