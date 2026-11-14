let mediaSessionToken = null;
let mediaSessionPromise = null;
export function resetMediaSession(){ mediaSessionToken = null; mediaSessionPromise = null; }
const rawApiRoot = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
const API_ROOT = rawApiRoot.replace(/\/+$/, "");

export function mediaUrl(path) {
  return path ? `${API_ROOT}${path}` : "";
}

function formatApiError(body, status) {
  const detail = Array.isArray(body?.detail)
    ? body.detail.map((item) => `${item.loc?.slice(1).join(".")}: ${item.msg}`).join("; ")
    : body?.detail;
  return detail || `Request failed (${status})`;
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
    const err = new Error(formatApiError(body, response.status));
    err.status = response.status;
    err.path = path;
    throw err;
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

export function apiUpload(path, formData, { workspaceId, signal, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const token = localStorage.getItem("token");
    const ws = workspaceId !== undefined ? workspaceId : localStorage.getItem("workspace_id");
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_ROOT}/api${path}`, true);
    xhr.withCredentials = true;
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    if (ws) xhr.setRequestHeader("X-Workspace-Id", ws);

    const handleAbort = () => {
      try { xhr.abort(); } catch {}
    };
    if (signal) {
      if (signal.aborted) {
        reject(new DOMException("Upload cancelled", "AbortError"));
        return;
      }
      signal.addEventListener("abort", handleAbort, { once: true });
    }

    xhr.upload.onprogress = (evt) => {
      if (onProgress) onProgress(evt.loaded || 0, evt.total || 0);
    };

    xhr.onload = () => {
      if (signal) signal.removeEventListener("abort", handleAbort);
      let body = {};
      try { body = JSON.parse(xhr.responseText || "{}"); } catch {}
      if (xhr.status === 401 && token) {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        localStorage.removeItem("role");
        resetMediaSession();
        window.location.replace("/login");
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body);
      } else {
        const err = new Error(formatApiError(body, xhr.status));
        err.status = xhr.status;
        err.path = path;
        reject(err);
      }
    };

    xhr.onerror = () => {
      if (signal) signal.removeEventListener("abort", handleAbort);
      reject(new Error("Network error while uploading batch."));
    };

    xhr.onabort = () => {
      if (signal) signal.removeEventListener("abort", handleAbort);
      reject(new DOMException("Upload cancelled", "AbortError"));
    };

    xhr.send(formData);
  });
}
