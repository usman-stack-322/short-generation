import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle2, FolderUp, Loader2, Minimize2, Maximize2, X, XCircle } from "lucide-react";
import { api, apiUpload } from "../services/api";
import {
  buildInstantVaultIndex,
  canonicalVaultRel,
  clearLocalVaultIndex,
  clearSavedDirectoryHandle,
  ensureDirectoryPermission,
  getCachedVaultManifest,
  getLocalVaultIndex,
  getSavedDirectoryHandle,
  saveCachedVaultManifest,
  saveDirectoryHandle,
  saveLocalVaultIndex,
  walkDirectoryHandleParallel,
} from "../utils/folderStore";

const ALLOWED_VAULT_EXT_RE = /\.(jpg|jpeg|png|webp|mp4|mov|webm|mkv|m4v)$/i;
const ALLOWED_LIBRARY_IMG_RE = /\.(jpe?g|png|webp)$/i;
const MAX_BATCH_FILES = 80;
const MAX_BATCH_BYTES = 45 * 1024 * 1024;
const LARGE_FILE_THRESHOLD = 45 * 1024 * 1024;
const CHUNK_BYTES = 16 * 1024 * 1024;
const CHUNK_CONCURRENCY = 3;
const VAULT_CONCURRENCY = 8;
const LIBRARY_CONCURRENCY = 8;

const UploadContext = createContext(null);

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 MB";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes < 1024 * 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  return `${(bytes / (1024 * 1024 * 1024 * 1024)).toFixed(2)} TB`;
}

function formatEta(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const s = Math.ceil(seconds);
  if (s < 60) return `${s}s left`;
  const m = Math.floor(s / 60);
  const remS = s % 60;
  if (m < 60) return remS > 0 ? `${m}m ${remS}s left` : `${m}m left`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return `${h}h ${remM}m left`;
}

function buildBatches(items) {
  const batches = [];
  let current = [];
  let currentBytes = 0;
  for (const item of items) {
    const size = item.file.size || 0;
    if (current.length >= MAX_BATCH_FILES || (current.length > 0 && currentBytes + size > MAX_BATCH_BYTES)) {
      batches.push(current);
      current = [];
      currentBytes = 0;
    }
    current.push(item);
    currentBytes += size;
  }
  if (current.length) batches.push(current);
  return batches;
}

async function runWithRetry(fn, signal, retries = 2) {
  let attempt = 0;
  while (true) {
    try {
      return await fn();
    } catch (err) {
      if (err?.name === "AbortError" || signal?.aborted) throw err;
      // Do not retry deterministic 4xx client/route errors (e.g. 401, 403, 404, 413, 422)
      if (err?.status >= 400 && err?.status < 500) throw err;
      attempt++;
      if (attempt > retries) throw err;
      await new Promise((r) => setTimeout(r, 700 * attempt));
    }
  }
}

export async function rescanVaultWithFallback({
  workspaceId,
  preference,
  signal,
  fallbackFolderPath = "",
  throwOnMissingFallback = false,
} = {}) {
  try {
    return await api("/assets/rescan", {
      method: "POST",
      signal,
      headers: workspaceId ? { "X-Workspace-Id": workspaceId } : {},
      body: JSON.stringify({ preference }),
    });
  } catch (err) {
    if (err?.status !== 404) throw err;
    if (fallbackFolderPath) {
      return await api("/assets/connect-folder", {
        method: "POST",
        signal,
        headers: workspaceId ? { "X-Workspace-Id": workspaceId } : {},
        body: JSON.stringify({ folder_path: fallbackFolderPath, preference }),
      });
    }
    if (throwOnMissingFallback) throw err;
    return null;
  }
}

export function UploadProvider({ children }) {
  const [vaultJob, setVaultJob] = useState(null);
  const [libraryJob, setLibraryJob] = useState(null);
  const [vaultVersion, setVaultVersion] = useState(0);
  const [libraryVersion, setLibraryVersion] = useState(0);
  const [minimized, setMinimized] = useState(false);
  const [savedFolder, setSavedFolder] = useState(null);
  const [localVaultIndex, setLocalVaultIndex] = useState(null);

  const vaultAbortRef = useRef(null);
  const libraryAbortRef = useRef(null);
  const localFilesMapRef = useRef(new Map());
  const localByCelebrityRef = useRef(new Map());
  const blobUrlCacheRef = useRef(new Map());

  const workspaceKey = () => localStorage.getItem("workspace_id") || JSON.parse(localStorage.getItem("user") || "{}").id || "default";

  useEffect(() => {
    if (!localStorage.getItem("token")) return;
    const wsKey = workspaceKey();
    getSavedDirectoryHandle(wsKey).then(setSavedFolder).catch(() => {});
    getLocalVaultIndex(wsKey)
      .then((idx) => {
        if (idx) setLocalVaultIndex((cur) => cur || idx);
      })
      .catch(() => {});
  }, []);

  const getLocalPreviewUrl = useCallback((relKey) => {
    if (!relKey) return "";
    const cached = blobUrlCacheRef.current.get(relKey);
    if (cached) return cached;
    const file = localFilesMapRef.current.get(relKey);
    if (!file) return "";
    try {
      if (blobUrlCacheRef.current.size >= 60) {
        const oldestKey = blobUrlCacheRef.current.keys().next().value;
        const oldestUrl = blobUrlCacheRef.current.get(oldestKey);
        if (oldestUrl) {
          try {
            URL.revokeObjectURL(oldestUrl);
          } catch {}
        }
        blobUrlCacheRef.current.delete(oldestKey);
      }
      const url = URL.createObjectURL(file);
      blobUrlCacheRef.current.set(relKey, url);
      return url;
    } catch {
      return "";
    }
  }, []);

  const getLocalFile = useCallback((relKey) => {
    if (!relKey) return null;
    return localFilesMapRef.current.get(relKey) || null;
  }, []);

  const matchLocalFileForScene = useCallback((scene, people = [], preference = "mix_both", usedRelKeys = new Set()) => {
    const byCeleb = localByCelebrityRef.current;
    if (!byCeleb || byCeleb.size === 0) return null;
    const haystack = [
      scene?.image_query || "",
      scene?.visual_description || "",
      scene?.on_screen_text || "",
      scene?.narration || "",
      ...(people || []),
    ]
      .join(" ")
      .toLowerCase();

    const sceneNum = Number(scene?.number || 1);
    const preferType =
      preference === "prefer_clips"
        ? "video"
        : preference === "prefer_images"
        ? "image"
        : sceneNum % 2 === 1
        ? "video"
        : "image";

    let bestItem = null;
    let bestScore = -1;

    for (const [celebLow, items] of byCeleb.entries()) {
      const tokens = celebLow.split(/\s+/).filter((t) => t.length >= 3);
      if (!tokens.length) continue;
      let celebScore = 0;
      if (haystack.includes(celebLow)) {
        celebScore = 200;
      } else if (tokens.length >= 2 && tokens.every((t) => haystack.includes(t))) {
        celebScore = 150;
      } else if (tokens.length >= 2 && haystack.includes(tokens[tokens.length - 1])) {
        celebScore = 95;
      }
      if (celebScore <= 0) continue;

      for (const item of items) {
        let score = celebScore;
        if (item.media_type === preferType) score += 20;
        for (const m of item.mood_tags || []) {
          if (haystack.includes(m)) score += 15;
        }
        // Prefer clips under 35 MB for instant scene attach
        if (item.media_type === "video" && item.file?.size > 35 * 1024 * 1024) {
          score -= 25;
        }
        if (usedRelKeys.has(item.relKey)) {
          score -= 500;
        }
        if (score > bestScore) {
          bestScore = score;
          bestItem = item;
        }
      }
    }
    return bestScore > 0 ? bestItem : null;
  }, []);

  const activeJobs = [vaultJob, libraryJob].filter(
    (j) => j && ["scanning", "checking", "uploading", "indexing"].includes(j.phase)
  );

  // Warn user only if closing the entire browser tab while an upload runs (switching pages keeps running!)
  useEffect(() => {
    if (activeJobs.length === 0) return;
    const onBeforeUnload = (e) => {
      e.preventDefault();
      e.returnValue = "Folder upload is still running in background. Leave anyway?";
      return e.returnValue;
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [activeJobs.length]);

  const cancelVaultUpload = useCallback(() => {
    vaultAbortRef.current?.abort();
  }, []);

  const cancelLibraryUpload = useCallback(() => {
    libraryAbortRef.current?.abort();
  }, []);

  const forgetSavedFolder = useCallback(async () => {
    const wsKey = workspaceKey();
    await clearSavedDirectoryHandle(wsKey);
    await clearLocalVaultIndex(wsKey);
    for (const url of blobUrlCacheRef.current.values()) {
      try { URL.revokeObjectURL(url); } catch {}
    }
    blobUrlCacheRef.current.clear();
    localFilesMapRef.current.clear();
    localByCelebrityRef.current.clear();
    setSavedFolder(null);
    setLocalVaultIndex(null);
  }, []);

  const dismissVaultJob = useCallback(() => {
    setVaultJob((cur) => (cur && ["done", "error", "cancelled"].includes(cur.phase) ? null : cur));
  }, []);

  const dismissLibraryJob = useCallback(() => {
    setLibraryJob((cur) => (cur && ["done", "error", "cancelled"].includes(cur.phase) ? null : cur));
  }, []);

  const executeVaultItems = useCallback(async (valid, { celebrityName = "", preference = "mix_both", controller, startedAt, workspaceId }) => {
    const wsCacheKey = workspaceId || workspaceKey();
    try {
      const t0 = performance.now();
      const { index, filesByRelKey, filesByCelebrity } = buildInstantVaultIndex(valid, celebrityName, preference);

      for (const url of blobUrlCacheRef.current.values()) {
        try { URL.revokeObjectURL(url); } catch {}
      }
      blobUrlCacheRef.current.clear();
      localFilesMapRef.current = filesByRelKey;
      localByCelebrityRef.current = filesByCelebrity;
      setLocalVaultIndex(index);
      saveLocalVaultIndex(wsCacheKey, index);

      const totalBytes = valid.reduce((sum, x) => sum + (x.file?.size || 0), 0);
      const elapsedMs = Math.max(12, Math.round(performance.now() - t0));

      setVaultVersion((v) => v + 1);
      setVaultJob({
        id: startedAt,
        title: "Celebrity Clips Sync",
        phase: "done",
        checkedFiles: valid.length,
        totalFiles: valid.length,
        uploadedFiles: index.total_assets,
        skippedFiles: 0,
        totalBytes,
        loadedBytes: totalBytes,
        speedBps: 0,
        startedAt,
        message: `Done in ${elapsedMs}ms! Indexed ${index.total_assets.toLocaleString()} clips across ${index.celebrities.length.toLocaleString()} celebrities — saved & ready for Shorts.`,
      });
    } catch (err) {
      const isCancelled = err?.name === "AbortError" || controller.signal.aborted;
      const errDetail = err?.path ? `${err?.message || "Sync failed."} (${err.status || "error"} · ${err.path})` : (err?.message || "Sync failed.");
      setVaultJob((cur) => ({
        ...(cur || {}),
        id: startedAt,
        title: "Celebrity Clips Sync",
        phase: isCancelled ? "cancelled" : "error",
        message: isCancelled ? "Folder sync stopped." : errDetail,
      }));
    } finally {
      if (vaultAbortRef.current === controller) {
        vaultAbortRef.current = null;
      }
    }
  }, []);

  const startVaultUpload = useCallback(async ({ rawItems, celebrityName = "", preference = "mix_both" }) => {
    const valid = (rawItems || []).filter(({ file, relPath }) => {
      const name = relPath || file?.name || "";
      const base = name.split(/[/\\]/).pop() || "";
      return ALLOWED_VAULT_EXT_RE.test(name) && !base.startsWith(".tmp_") && (file?.size || 0) > 0;
    });
    if (!valid.length) {
      setVaultJob({
        id: Date.now(),
        title: "Celebrity Clips Sync",
        phase: "error",
        message: "No supported image (.jpg/.png/.webp) or video (.mp4/.mov/.webm) files found.",
        totalFiles: 0,
        uploadedFiles: 0,
        skippedFiles: 0,
        totalBytes: 0,
        loadedBytes: 0,
      });
      return;
    }

    if (vaultAbortRef.current) vaultAbortRef.current.abort();
    const controller = new AbortController();
    vaultAbortRef.current = controller;
    const workspaceId = localStorage.getItem("workspace_id") || "";
    const startedAt = Date.now();
    setMinimized(false);
    await executeVaultItems(valid, { celebrityName, preference, controller, startedAt, workspaceId });
  }, [executeVaultItems]);

  const startVaultUploadFromHandle = useCallback(async (dirHandle, { celebrityName = "", preference = "mix_both", skipPermissionCheck = false } = {}) => {
    if (!dirHandle) return;
    let ok = true;
    if (!skipPermissionCheck) {
      try {
        ok = await ensureDirectoryPermission(dirHandle);
      } catch {
        ok = typeof dirHandle.entries === "function";
      }
    }
    if (!ok) {
      setVaultJob({
        id: Date.now(),
        title: "Celebrity Clips Sync",
        phase: "error",
        message: "Folder read permission was denied. Try Browse Folder instead.",
        totalFiles: 0,
        totalBytes: 0,
        loadedBytes: 0,
      });
      return;
    }

    if (vaultAbortRef.current) vaultAbortRef.current.abort();
    const controller = new AbortController();
    vaultAbortRef.current = controller;
    const workspaceId = localStorage.getItem("workspace_id") || "";
    const startedAt = Date.now();
    setMinimized(false);

    setVaultJob({
      id: startedAt,
      title: "Celebrity Clips Sync",
      phase: "scanning",
      checkedFiles: 0,
      totalFiles: 0,
      totalBytes: 0,
      loadedBytes: 0,
      startedAt,
      message: `Scanning "${dirHandle.name}"… 0 clips found`,
    });

    // Save handle immediately so 100GB+ folders remain one-click resumable even if stopped early.
    await saveDirectoryHandle(workspaceKey(), dirHandle, 0);
    setSavedFolder({ handle: dirHandle, name: dirHandle.name, totalFound: 0, savedAt: Date.now() });

    try {
      const valid = await walkDirectoryHandleParallel(
        dirHandle,
        (count) => {
          setVaultJob((cur) => cur && cur.id === startedAt ? {
            ...cur,
            checkedFiles: count,
            message: `Scanning "${dirHandle.name}"… ${count.toLocaleString()} clips found`,
          } : cur);
        },
        controller.signal
      );

      if (!valid.length) {
        setVaultJob({
          id: startedAt,
          title: "Celebrity Clips Sync",
          phase: "error",
          message: `No supported photos or video clips found inside "${dirHandle.name}".`,
          totalFiles: 0,
          totalBytes: 0,
          loadedBytes: 0,
        });
        return;
      }

      await saveDirectoryHandle(workspaceKey(), dirHandle, valid.length);
      setSavedFolder({ handle: dirHandle, name: dirHandle.name, totalFound: valid.length, savedAt: Date.now() });
      await executeVaultItems(valid, { celebrityName, preference, controller, startedAt, workspaceId });
    } catch (err) {
      const isCancelled = err?.name === "AbortError" || controller.signal.aborted;
      setVaultJob({
        id: startedAt,
        title: "Celebrity Clips Sync",
        phase: isCancelled ? "cancelled" : "error",
        message: isCancelled ? "Folder scan stopped." : err?.message || "Failed to read folder.",
        totalFiles: 0,
        totalBytes: 0,
        loadedBytes: 0,
      });
    } finally {
      if (vaultAbortRef.current === controller) vaultAbortRef.current = null;
    }
  }, [executeVaultItems]);

  const startLibraryUpload = useCallback(async ({ collectionId, collectionName = "Collection", rawFiles }) => {
    const valid = Array.from(rawFiles || []).filter(
      (file) => ALLOWED_LIBRARY_IMG_RE.test(file.name) && (file.size || 0) > 0
    );
    if (!valid.length || !collectionId) return;

    if (libraryAbortRef.current) libraryAbortRef.current.abort();
    const controller = new AbortController();
    libraryAbortRef.current = controller;
    const workspaceId = localStorage.getItem("workspace_id") || "";
    const startedAt = Date.now();
    setMinimized(false);

    setLibraryJob({
      id: startedAt,
      title: `Media Import (${collectionName})`,
      phase: "checking",
      message: `Checking ${valid.length} images for duplicates…`,
      totalFiles: valid.length,
      uploadedFiles: 0,
      skippedFiles: 0,
      totalBytes: valid.reduce((sum, f) => sum + (f.size || 0), 0),
      loadedBytes: 0,
      startedAt,
    });

    try {
      const existingIndices = new Set();
      const CHECK_CHUNK = 1000;
      try {
        for (let offset = 0; offset < valid.length; offset += CHECK_CHUNK) {
          if (controller.signal.aborted) throw new DOMException("Upload cancelled", "AbortError");
          const slice = valid.slice(offset, offset + CHECK_CHUNK);
          const res = await api(`/library/collections/${collectionId}/check-existing`, {
            method: "POST",
            signal: controller.signal,
            headers: workspaceId ? { "X-Workspace-Id": workspaceId } : {},
            body: JSON.stringify({
              items: slice.map((f) => ({ name: f.name, size: f.size || 0 })),
            }),
          });
          for (const relIdx of res.existing_indices || []) {
            existingIndices.add(offset + relIdx);
          }
        }
      } catch (checkErr) {
        if (checkErr?.name === "AbortError" || controller.signal.aborted) throw checkErr;
        if (checkErr?.status !== 404) throw checkErr;
      }

      const toUpload = valid.filter((_, idx) => !existingIndices.has(idx));
      const skippedCount = existingIndices.size;

      if (toUpload.length === 0) {
        setLibraryVersion((v) => v + 1);
        setLibraryJob({
          id: startedAt,
          title: `Media Import (${collectionName})`,
          phase: "done",
          message: `All ${skippedCount} images are already in this collection.`,
          totalFiles: valid.length,
          uploadedFiles: 0,
          skippedFiles: skippedCount,
          totalBytes: 0,
          loadedBytes: 0,
        });
        return;
      }

      const totalUploadBytes = toUpload.reduce((sum, f) => sum + (f.size || 0), 0);
      const fileLoaded = new Array(toUpload.length).fill(0);
      let nextIdx = 0;
      let imported = 0;
      let failed = 0;
      let lastTick = 0;

      const syncUi = (force = false) => {
        const now = Date.now();
        if (!force && now - lastTick < 150) return;
        lastTick = now;
        const loaded = fileLoaded.reduce((a, b) => a + b, 0);
        setLibraryJob((cur) => cur && cur.id === startedAt ? {
          ...cur,
          phase: "uploading",
          uploadedFiles: imported,
          skippedFiles: skippedCount,
          totalBytes: totalUploadBytes,
          loadedBytes: Math.min(loaded, totalUploadBytes),
          message: `Uploading ${imported}/${toUpload.length} images${skippedCount ? ` (${skippedCount} skipped)` : ""}${failed ? ` · ${failed} failed` : ""}`,
        } : cur);
      };

      syncUi(true);

      const worker = async () => {
        while (true) {
          if (controller.signal.aborted) return;
          const idx = nextIdx++;
          if (idx >= toUpload.length) return;
          const file = toUpload[idx];
          try {
            await runWithRetry(async () => {
              const body = new FormData();
              body.set("file", file);
              body.set("name", file.name.slice(0, 160));
              body.set("creator", "Member supplied");
              body.set("rights_confirmed", "true");
              body.set("license", "Own work");
              return apiUpload(`/library/collections/${collectionId}/media`, body, {
                workspaceId,
                signal: controller.signal,
                onProgress: (loaded) => {
                  fileLoaded[idx] = Math.min(loaded, file.size || loaded);
                  syncUi(false);
                },
              });
            }, controller.signal, 1);
            fileLoaded[idx] = file.size || 0;
            imported++;
          } catch (err) {
            if (err?.name === "AbortError" || controller.signal.aborted) throw err;
            failed++;
          }
          syncUi(true);
        }
      };

      const count = Math.min(LIBRARY_CONCURRENCY, toUpload.length);
      await Promise.all(Array.from({ length: count }, () => worker()));

      setLibraryVersion((v) => v + 1);
      setLibraryJob({
        id: startedAt,
        title: `Media Import (${collectionName})`,
        phase: failed && imported === 0 ? "error" : "done",
        message: `Imported ${imported} images${skippedCount ? `, skipped ${skippedCount} duplicates` : ""}${failed ? `, ${failed} failed` : ""}.`,
        totalFiles: valid.length,
        uploadedFiles: imported,
        skippedFiles: skippedCount,
        totalBytes: totalUploadBytes,
        loadedBytes: totalUploadBytes,
      });
    } catch (err) {
      const isCancelled = err?.name === "AbortError" || controller.signal.aborted;
      setLibraryVersion((v) => v + 1);
      setLibraryJob((cur) => ({
        ...(cur || {}),
        id: startedAt,
        title: `Media Import (${collectionName})`,
        phase: isCancelled ? "cancelled" : "error",
        message: isCancelled
          ? "Import stopped. Completed images were saved."
          : err?.message || "Import failed.",
      }));
    } finally {
      if (libraryAbortRef.current === controller) libraryAbortRef.current = null;
    }
  }, []);

  const visibleJobs = [
    vaultJob && { ...vaultJob, key: "vault", cancel: cancelVaultUpload, dismiss: dismissVaultJob },
    libraryJob && { ...libraryJob, key: "library", cancel: cancelLibraryUpload, dismiss: dismissLibraryJob },
  ].filter(Boolean);

  return (
    <UploadContext.Provider
      value={{
        vaultJob,
        libraryJob,
        vaultVersion,
        libraryVersion,
        savedFolder,
        setSavedFolder,
        forgetSavedFolder,
        localVaultIndex,
        getLocalPreviewUrl,
        getLocalFile,
        matchLocalFileForScene,
        startVaultUpload,
        startVaultUploadFromHandle,
        startLibraryUpload,
        cancelVaultUpload,
        cancelLibraryUpload,
        dismissVaultJob,
        dismissLibraryJob,
      }}
    >
      {children}
      {visibleJobs.length > 0 && localStorage.getItem("token") && (
        <aside className={`global-upload-dock ${minimized ? "minimized" : ""}`} aria-live="polite">
          <div className="global-upload-head">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <FolderUp size={15} />
              <strong>
                {activeJobs.length > 0
                  ? `Background Uploads (${activeJobs.length} active)`
                  : "Upload Summary"}
              </strong>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label={minimized ? "Expand upload status" : "Minimize upload status"}
              onClick={() => setMinimized((m) => !m)}
            >
              {minimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
            </button>
          </div>
          {!minimized && (
            <div className="global-upload-list">
              {visibleJobs.map((job) => {
                const active = ["scanning", "checking", "uploading", "indexing"].includes(job.phase);
                const pct =
                  job.phase === "checking" && job.totalFiles > 0
                    ? Math.min(100, Math.round(((job.checkedFiles || 0) / job.totalFiles) * 100))
                    : job.totalBytes > 0
                    ? Math.min(100, Math.round((job.loadedBytes / job.totalBytes) * 100))
                    : job.phase === "done"
                    ? 100
                    : 0;
                return (
                  <div key={job.key} className="global-upload-item">
                    <div className="global-upload-row">
                      <span className="global-upload-title">
                        {active && <Loader2 size={13} className="spin" />}
                        {job.phase === "done" && <CheckCircle2 size={13} color="#16a34a" />}
                        {(job.phase === "error" || job.phase === "cancelled") && <XCircle size={13} color="#dc2626" />}
                        <span>{job.title}</span>
                      </span>
                      {active ? (
                        <button type="button" className="global-upload-action" onClick={job.cancel}>
                          Cancel
                        </button>
                      ) : (
                        <button type="button" className="icon-button" aria-label="Dismiss" onClick={job.dismiss}>
                          <X size={13} />
                        </button>
                      )}
                    </div>
                    {active && (
                      <>
                        <div className="global-upload-bar">
                          <div className="global-upload-bar-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="global-upload-meta">
                          <span>{pct}%</span>
                          {job.phase === "uploading" && job.totalBytes > 0 && (
                            <span>
                              {formatBytes(job.loadedBytes)} / {formatBytes(job.totalBytes)}
                              {job.speedBps > 0 ? ` · ${formatBytes(job.speedBps)}/s` : ""}
                            </span>
                          )}
                        </div>
                      </>
                    )}
                    <p className="global-upload-msg">{job.message}</p>
                  </div>
                );
              })}
            </div>
          )}
        </aside>
      )}
    </UploadContext.Provider>
  );
}

export function useUploads() {
  const ctx = useContext(UploadContext);
  if (!ctx) throw new Error("useUploads must be used inside UploadProvider");
  return ctx;
}
