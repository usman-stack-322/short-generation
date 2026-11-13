let mediaSessionToken = null;
let mediaSessionPromise = null;
export function resetMediaSession(){ mediaSessionToken = null; mediaSessionPromise = null; }
const rawApiRoot = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
const API_ROOT = rawApiRoot.replace(/\/+$/, "");

export function mediaUrl(path) {
  return path ? `${API_ROOT}${path}` : "";
}

export async function api(path, options = {}) {
  const token = localStorage.getItem("token");
  const workspaceId = localStorage.getItem("workspace_id");
  const response = await fetch(`${API_ROOT}/api${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (response.status === 401 && token && !["/auth/login", "/auth/forgot-password", "/auth/reset-password"].includes(path)) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('role');
    resetMediaSession();
    window.location.replace('/login');
  }
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((item) => `${item.loc?.slice(1).join(".")}: ${item.msg}`).join("; ") : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  if (token && path !== '/auth/media-session') {
    if (mediaSessionToken !== token) {
      mediaSessionToken = token;
      mediaSessionPromise = fetch(`${API_ROOT}/api/auth/media-session`, { method: 'POST', credentials: 'include', headers: { Authorization: `Bearer ${token}` } }).then(response => { if (!response.ok) throw new Error('Media session unavailable'); }).catch(error => { mediaSessionToken = null; throw error; });
    }
    await mediaSessionPromise;
  }
  return body;
}
