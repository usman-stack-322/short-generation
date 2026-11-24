export const API_BASE = (
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  'http://127.0.0.1:8000'
)
  .trim()
  .replace(/\/+$/, '');

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
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
    const message =
      (data && (data.detail || data.message)) ||
      `Request failed with HTTP ${response.status}`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

export function getHealth() {
  return requestJson('/api/health');
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
  return `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/video`;
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
