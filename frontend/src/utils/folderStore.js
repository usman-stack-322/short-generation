const DB_NAME = "ai_shorts_vault_handles";
const STORE_NAME = "handles";
const ALLOWED_VAULT_EXT_RE = /\.(jpg|jpeg|png|webp|mp4|mov|webm|mkv|m4v)$/i;

const GENERIC_SUBFOLDERS = new Set([
  "videos", "video", "clips", "clip", "images", "image", "photos", "photo",
  "pics", "pic", "pictures", "media", "raw", "broll", "b roll", "b-roll",
  "assets", "celebrities", "celebrity", "data", "new folder", "untitled folder",
  "int", "ints", "intro", "outro", "interview", "interviews", "podcast", "podcasts",
  "highlights", "highlight", "reaction", "reactions", "short", "shorts",
  "cut", "cuts", "archive", "old", "new", "extra", "extras", "temp", "misc",
]);

export function canonicalVaultRel(rawPath, overrideCelebrity = "") {
  const clean = String(rawPath || "asset").replace(/\\/g, "/");
  const segs = clean.split("/").filter((p) => p && p !== "." && p !== "..");
  const fileName = segs[segs.length - 1] || "asset";
  if (fileName.startsWith(".tmp_") || !ALLOWED_VAULT_EXT_RE.test(fileName)) return "";

  const celeb = overrideCelebrity.trim().replace(/[\\/:*?"<>|]/g, "");
  if (celeb) {
    return `${celeb}/${fileName}`.toLowerCase();
  }
  const parts = segs.slice(0, -1);
  if (parts.length >= 2) {
    const subParts = parts.slice(1);
    if (subParts.some((p) => !GENERIC_SUBFOLDERS.has(p.toLowerCase()))) {
      return `${subParts.join("/")}/${fileName}`.toLowerCase();
    }
  }
  if (parts.length > 0) {
    return `${parts.join("/")}/${fileName}`.toLowerCase();
  }
  return fileName.toLowerCase();
}

function openHandleDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveDirectoryHandle(workspaceKey, handle, totalFound = 0) {
  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(
        { handle, name: handle.name, totalFound, savedAt: Date.now() },
        workspaceKey || "default"
      );
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {}
}

export async function getSavedDirectoryHandle(workspaceKey) {
  try {
    const db = await openHandleDb();
    const record = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(workspaceKey || "default");
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return record;
  } catch {
    return null;
  }
}

export async function clearSavedDirectoryHandle(workspaceKey) {
  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(workspaceKey || "default");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {}
}

export async function ensureDirectoryPermission(handle) {
  if (!handle) return false;
  try {
    if (typeof handle.queryPermission !== "function") return true;
    const current = await handle.queryPermission({ mode: "read" });
    if (current === "granted") return true;
    if (typeof handle.requestPermission !== "function") return current !== "denied";
    return (await handle.requestPermission({ mode: "read" })) === "granted";
  } catch {
    // Handles returned directly from showDirectoryPicker already grant read access for the current session.
    return typeof handle.entries === "function";
  }
}

export async function walkDirectoryHandleParallel(dirHandle, onProgress, signal) {
  const queue = [{ handle: dirHandle, prefix: dirHandle.name }];
  const items = [];
  let lastTick = 0;

  async function processDir({ handle, prefix }) {
    if (signal?.aborted) return;
    const filePromises = [];
    try {
      for await (const [name, entry] of handle.entries()) {
        if (signal?.aborted) return;
        if (entry.kind === "directory") {
          const low = name.toLowerCase();
          if (!name.startsWith(".tmp_") && !name.startsWith("$") && low !== "system volume information") {
            queue.push({ handle: entry, prefix: `${prefix}/${name}` });
          }
        } else if (entry.kind === "file" && ALLOWED_VAULT_EXT_RE.test(name) && !name.startsWith(".tmp_")) {
          filePromises.push(
            entry.getFile().then((file) => {
              if (file && file.size > 0) {
                items.push({ file, relPath: `${prefix}/${name}` });
              }
            }).catch(() => {})
          );
          if (filePromises.length >= 64) {
            await Promise.all(filePromises.splice(0));
            const now = Date.now();
            if (onProgress && now - lastTick > 80) {
              lastTick = now;
              onProgress(items.length);
            }
          }
        }
      }
    } catch {
      // Skip protected or system subdirectories instead of aborting the entire folder scan.
    }
    if (filePromises.length) {
      await Promise.all(filePromises);
    }
    const now = Date.now();
    if (onProgress && now - lastTick > 80) {
      lastTick = now;
      onProgress(items.length);
    }
  }

  // Drain BFS directory queue with up to 6 concurrent directory scanners
  while (queue.length > 0) {
    if (signal?.aborted) throw new DOMException("Upload cancelled", "AbortError");
    const wave = queue.splice(0, 6);
    await Promise.all(wave.map((node) => processDir(node)));
  }
  if (onProgress) onProgress(items.length);
  return items;
}
