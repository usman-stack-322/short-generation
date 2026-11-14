import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle2, FolderUp, Loader2, Minimize2, Maximize2, X, XCircle } from "lucide-react";
import { api, apiUpload } from "../services/api";
import {
  canonicalVaultRel,
  clearSavedDirectoryHandle,
  ensureDirectoryPermission,
  getSavedDirectoryHandle,
  saveDirectoryHandle,
  walkDirectoryHandleParallel,
} from "../utils/folderStore";

const ALLOWED_VAULT_EXT_RE = /\.(jpg|jpeg|png|webp|mp4|mov|webm|mkv|m4v)$/i;
const ALLOWED_LIBRARY_IMG_RE = /\.(jpe?g|png|webp)$/i;
const MAX_BATCH_FILES = 25;
const MAX_BATCH_BYTES = 15 * 1024 * 1024;
const LARGE_FILE_THRESHOLD = 15 * 1024 * 1024;
const CHUNK_BYTES = 8 * 1024 * 1024;
const VAULT_CONCURRENCY = 6;
const LIBRARY_CONCURRENCY = 4;

const UploadContext = createContext(null);

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 MB";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes < 1024 * 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  return `${(bytes / (1024 * 1024 * 1024 * 1024)).toFixed(2)} TB`;
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

  const vaultAbortRef = useRef(null);
  const libraryAbortRef = useRef(null);

  const workspaceKey = () => localStorage.getItem("workspace_id") || JSON.parse(localStorage.getItem("user") || "{}").id || "default";

  useEffect(() => {
    if (!localStorage.getItem("token")) return;
    getSavedDirectoryHandle(workspaceKey()).then(setSavedFolder).catch(() => {});
  }, [vaultVersion]);

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
    await clearSavedDirectoryHandle(workspaceKey());
    setSavedFolder(null);
  }, []);

  const dismissVaultJob = useCallback(() => {
    setVaultJob((cur) => (cur && ["done", "error", "cancelled"].includes(cur.phase) ? null : cur));
  }, []);

  const dismissLibraryJob = useCallback(() => {
    setLibraryJob((cur) => (cur && ["done", "error", "cancelled"].includes(cur.phase) ? null : cur));
  }, []);

  const executeVaultItems = useCallback(async (valid, { celebrityName = "", preference = "mix_both", controller, startedAt, workspaceId }) => {
    let uploadedFilesCount = 0;
    try {
      setVaultJob({
        id: startedAt,
        title: "Celebrity Clips Sync",
        phase: "checking",
        checkedFiles: 0,
        totalFiles: valid.length,
        uploadedFiles: 0,
        skippedFiles: 0,
        totalBytes: 0,
        loadedBytes: 0,
        speedBps: 0,
        startedAt,
        message: `Checking clips 0 / ${valid.length}…`,
      });

      // Fast compressed O(1) manifest comparison; degrade cleanly if backend lacks /assets/manifest
      let existingMap = {};
      let serverFolderPath = "";
      try {
        const manifestRes = await api("/assets/manifest", {
          signal: controller.signal,
          headers: workspaceId ? { "X-Workspace-Id": workspaceId } : {},
        });
        existingMap = manifestRes?.files || {};
        serverFolderPath = manifestRes?.folder_path || "";
      } catch (manifestErr) {
        if (manifestErr?.name === "AbortError" || controller.signal.aborted) throw manifestErr;
        if (manifestErr?.status !== 404) throw manifestErr;
      }
      const toUpload = [];
      let skippedCount = 0;

      const STEP = 350;
      for (let i = 0; i < valid.length; i++) {
        if (controller.signal.aborted) throw new DOMException("Upload cancelled", "AbortError");
        const item = valid[i];
        const relKey = canonicalVaultRel(item.relPath || item.file.webkitRelativePath || item.file.name, celebrityName);
        const remoteSize = existingMap[relKey];
        if (remoteSize && remoteSize === item.file.size) {
          skippedCount++;
        } else {
          toUpload.push(item);
        }
        if ((i + 1) % STEP === 0 || i === valid.length - 1) {
          const checked = i + 1;
          setVaultJob((cur) => cur && cur.id === startedAt ? {
            ...cur,
            phase: "checking",
            checkedFiles: checked,
            totalFiles: valid.length,
            skippedFiles: skippedCount,
            message: `Checking clips ${checked} / ${valid.length}`,
          } : cur);
          if (i < valid.length - 1) {
            await new Promise((r) => setTimeout(r, 0));
          }
        }
      }

      if (toUpload.length === 0) {
        setVaultJob((cur) => cur && {
          ...cur,
          phase: "indexing",
          skippedFiles: skippedCount,
          message: `All ${skippedCount} clips verified — refreshing index…`,
        });
        const scan = await rescanVaultWithFallback({
          workspaceId,
          preference,
          signal: controller.signal,
          fallbackFolderPath: serverFolderPath,
        });
        const totalIndexed = typeof scan?.total_assets === "number" ? scan.total_assets : skippedCount;
        setVaultVersion((v) => v + 1);
        setVaultJob({
          id: startedAt,
          title: "Celebrity Clips Sync",
          phase: "done",
          checkedFiles: valid.length,
          totalFiles: valid.length,
          uploadedFiles: 0,
          skippedFiles: skippedCount,
          totalBytes: 0,
          loadedBytes: 0,
          speedBps: 0,
          startedAt,
          message: `All ${skippedCount.toLocaleString()} clips already up to date (${totalIndexed.toLocaleString()} total indexed).`,
        });
        return;
      }

      // Parallel 6-worker upload: small clips in 15MB batches, large videos in resumable 8MB chunks
      const smallItems = [];
      const largeItems = [];
      for (const item of toUpload) {
        if ((item.file.size || 0) > LARGE_FILE_THRESHOLD) {
          largeItems.push(item);
        } else {
          smallItems.push(item);
        }
      }
      const uploadTasks = [
        ...buildBatches(smallItems).map((batch) => ({ kind: "batch", items: batch })),
        ...largeItems.map((item) => ({ kind: "chunked", item })),
      ];
      const totalUploadBytes = toUpload.reduce((sum, x) => sum + (x.file.size || 0), 0);
      const taskLoaded = new Array(uploadTasks.length).fill(0);
      const taskTotals = uploadTasks.map((t) =>
        t.kind === "batch"
          ? t.items.reduce((sum, x) => sum + (x.file.size || 0), 0)
          : t.item.file.size || 0
      );
      let nextTaskIndex = 0;
      let skippedOnServer = 0;
      let chunkEndpointMissing = false;
      let lastUiTick = 0;
      let lastLiveRefreshMs = Date.now();
      let lastRefreshedCount = 0;
      const uploadStartMs = Date.now();

      const updateProgress = (force = false) => {
        const now = Date.now();
        if (!force && now - lastUiTick < 120) return;
        lastUiTick = now;
        if (uploadedFilesCount > lastRefreshedCount && now - lastLiveRefreshMs > 15000) {
          lastLiveRefreshMs = now;
          lastRefreshedCount = uploadedFilesCount;
          setVaultVersion((v) => v + 1);
        }
        const loaded = taskLoaded.reduce((a, b) => a + b, 0);
        const elapsedSec = Math.max(0.2, (now - uploadStartMs) / 1000);
        setVaultJob((cur) => {
          if (!cur || cur.id !== startedAt) return cur;
          return {
            ...cur,
            phase: "uploading",
            checkedFiles: valid.length,
            totalFiles: valid.length,
            newFilesTotal: toUpload.length,
            uploadedFiles: uploadedFilesCount,
            skippedFiles: skippedCount + skippedOnServer,
            totalBytes: totalUploadBytes,
            loadedBytes: Math.min(loaded, totalUploadBytes),
            speedBps: loaded / elapsedSec,
            message: `Uploading clips ${uploadedFilesCount.toLocaleString()}/${toUpload.length.toLocaleString()}${skippedCount ? ` · ${skippedCount.toLocaleString()} already saved skipped` : ""}`,
          };
        });
      };

      updateProgress(true);

      const uploadBulkBatch = (taskIdx, batch) =>
        runWithRetry(async () => {
          const fd = new FormData();
          fd.append("celebrity_name", celebrityName);
          fd.append("skip_scan", "true");
          fd.append("skip_existing", "true");
          for (const { file, relPath } of batch) {
            fd.append("files", file, relPath || file.webkitRelativePath || file.name);
          }
          return apiUpload("/assets/upload-bulk", fd, {
            workspaceId,
            signal: controller.signal,
            onProgress: (loaded, total) => {
              taskLoaded[taskIdx] = Math.min(loaded, total || taskTotals[taskIdx]);
              updateProgress(false);
            },
          });
        }, controller.signal);

      const uploadChunkedLargeFile = async (taskIdx, item) => {
        if (chunkEndpointMissing) {
          return uploadBulkBatch(taskIdx, [item]);
        }
        const { file, relPath } = item;
        const totalSize = file.size || 0;
        const totalChunks = Math.max(1, Math.ceil(totalSize / CHUNK_BYTES));
        const uploadId = `${Date.now().toString(36)}_${taskIdx}_${Math.random().toString(36).slice(2, 10)}`;
        const resolvedRel = relPath || file.webkitRelativePath || file.name;
        let finalRes = null;

        try {
          for (let chunkIdx = 0; chunkIdx < totalChunks; chunkIdx++) {
            if (controller.signal.aborted) return finalRes;
            const start = chunkIdx * CHUNK_BYTES;
            const end = Math.min(totalSize, start + CHUNK_BYTES);
            const slice = file.slice(start, end);

            finalRes = await runWithRetry(async () => {
              const fd = new FormData();
              fd.append("relative_path", resolvedRel);
              fd.append("celebrity_name", celebrityName);
              fd.append("upload_id", uploadId);
              fd.append("chunk_index", String(chunkIdx));
              fd.append("total_chunks", String(totalChunks));
              fd.append("total_size", String(totalSize));
              fd.append("file", slice, file.name);
              return apiUpload("/assets/upload-chunk", fd, {
                workspaceId,
                signal: controller.signal,
                onProgress: (loaded) => {
                  taskLoaded[taskIdx] = Math.min(totalSize, start + loaded);
                  updateProgress(false);
                },
              });
            }, controller.signal);

            if (finalRes?.skipped) {
              taskLoaded[taskIdx] = totalSize;
              return finalRes;
            }
            taskLoaded[taskIdx] = end;
            updateProgress(false);
          }
          return finalRes;
        } catch (chunkErr) {
          if (chunkErr?.status === 404) {
            // Live backend hasn't rolled out /assets/upload-chunk yet; fall back cleanly to upload-bulk
            chunkEndpointMissing = true;
            taskLoaded[taskIdx] = 0;
            return uploadBulkBatch(taskIdx, [item]);
          }
          throw chunkErr;
        }
      };

      const worker = async () => {
        while (true) {
          if (controller.signal.aborted) return;
          const idx = nextTaskIndex++;
          if (idx >= uploadTasks.length) return;
          const task = uploadTasks[idx];

          let res;
          if (task.kind === "chunked") {
            res = await uploadChunkedLargeFile(idx, task.item);
            taskLoaded[idx] = taskTotals[idx];
            uploadedFilesCount += res?.saved ?? 1;
            skippedOnServer += res?.skipped ?? 0;
          } else {
            const batch = task.items;
            res = await uploadBulkBatch(idx, batch);
            taskLoaded[idx] = taskTotals[idx];
            uploadedFilesCount += res?.saved ?? batch.length;
            skippedOnServer += res?.skipped ?? 0;
          }
          if (res?.folder_path) serverFolderPath = res.folder_path;
          updateProgress(true);
        }
      };

      const workerCount = Math.min(VAULT_CONCURRENCY, uploadTasks.length);
      await Promise.all(Array.from({ length: workerCount }, () => worker()));

      setVaultJob((cur) => cur && {
        ...cur,
        phase: "indexing",
        loadedBytes: totalUploadBytes,
        message: "Finalizing library index…",
      });
      const scan = await rescanVaultWithFallback({
        workspaceId,
        preference,
        fallbackFolderPath: serverFolderPath,
      });
      const totalIndexedCount =
        typeof scan?.total_assets === "number"
          ? scan.total_assets
          : uploadedFilesCount + skippedCount + skippedOnServer;
      setVaultVersion((v) => v + 1);
      setVaultJob({
        id: startedAt,
        title: "Celebrity Clips Sync",
        phase: "done",
        checkedFiles: valid.length,
        totalFiles: valid.length,
        uploadedFiles: uploadedFilesCount,
        skippedFiles: skippedCount + skippedOnServer,
        totalBytes: totalUploadBytes,
        loadedBytes: totalUploadBytes,
        speedBps: 0,
        startedAt,
        message: `Done! Uploaded ${uploadedFilesCount.toLocaleString()} new clips${skippedCount ? `, skipped ${skippedCount.toLocaleString()} existing` : ""}. Total indexed: ${totalIndexedCount.toLocaleString()}.`,
      });
    } catch (err) {
      const isCancelled = err?.name === "AbortError" || controller.signal.aborted;
      if (isCancelled || uploadedFilesCount > 0) {
        try {
          await rescanVaultWithFallback({
            workspaceId,
            preference,
            fallbackFolderPath: serverFolderPath,
          });
          setVaultVersion((v) => v + 1);
        } catch {}
      }
      const errDetail = err?.path ? `${err?.message || "Upload failed."} (${err.status || "error"} · ${err.path})` : (err?.message || "Upload failed.");
      setVaultJob((cur) => ({
        ...(cur || {}),
        id: startedAt,
        title: "Celebrity Clips Sync",
        phase: isCancelled ? "cancelled" : "error",
        message: isCancelled
          ? "Upload stopped — completed files were saved & indexed. Re-select or re-sync anytime to resume."
          : `${errDetail}${uploadedFilesCount > 0 ? ` (${uploadedFilesCount} completed clips saved — re-sync to continue.)` : ""}`,
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
