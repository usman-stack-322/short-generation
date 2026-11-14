const DB_NAME = "ai_shorts_vault_handles";
const STORE_NAME = "handles";
const ALLOWED_VAULT_EXT_RE = /\.(jpg|jpeg|png|webp|mp4|mov|webm|mkv|m4v)$/i;
const VIDEO_EXT_RE = /\.(mp4|mov|webm|mkv|m4v)$/i;

const GENERIC_SUBFOLDERS = new Set([
  "videos", "video", "clips", "clip", "images", "image", "photos", "photo",
  "pics", "pic", "pictures", "media", "raw", "broll", "b roll", "b-roll",
  "assets", "celebrities", "celebrity", "data", "new folder", "untitled folder",
  "int", "ints", "intro", "outro", "interview", "interviews", "podcast", "podcasts",
  "highlights", "highlight", "reaction", "reactions", "short", "shorts",
  "cut", "cuts", "archive", "old", "new", "extra", "extras", "temp", "misc",
]);

const MOOD_KEYWORDS = new Set([
  "angry", "happy", "sad", "shocked", "laugh", "laughing", "smile", "smiling",
  "serious", "cry", "crying", "interview", "speech", "celebration", "celebrate",
  "fight", "argue", "arguing", "debate", "reaction", "podcast", "press",
  "game", "win", "loss", "highlight", "highlights", "dunk", "shot", "closeup",
  "intro", "outro", "int",
]);

function toTitleCase(str) {
  return String(str || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function cleanFolderName(raw) {
  let s = String(raw || "")
    .replace(/[→←•|]+/g, " ")
    .replace(/_/g, " ")
    .replace(/\s*-\s*/g, " ")
    .replace(/\s+\(\d+\)$/, "")
    .replace(/\s+\bnew\b(?:\s+\d{1,4})?$/i, "");
  if (!/^\d+\s/.test(s.trim())) {
    s = s.replace(/\s+\d{1,2}$/, "");
  }
  s = s.replace(/\s+/g, " ").trim();
  if (["new folder", "untitled folder", "copy"].includes(s.toLowerCase())) {
    return "";
  }
  return s;
}

export function parseCelebrityAndMood(rawPath, overrideCelebrity = "") {
  const clean = String(rawPath || "asset").replace(/\\/g, "/");
  const segs = clean.split("/").filter((p) => p && p !== "." && p !== "..");
  const fileName = segs[segs.length - 1] || "asset";
  const dotIdx = fileName.lastIndexOf(".");
  const stem = dotIdx > 0 ? fileName.slice(0, dotIdx) : fileName;
  const ext = dotIdx > 0 ? fileName.slice(dotIdx).toLowerCase() : "";
  const mediaType = VIDEO_EXT_RE.test(fileName) ? "video" : "image";

  const stemTokens = stem.toLowerCase().split(/[_\-\s.]+/).filter(Boolean);
  const moods = new Set(stemTokens.filter((t) => MOOD_KEYWORDS.has(t)));

  if (overrideCelebrity && overrideCelebrity.trim()) {
    const cleanedOverride = cleanFolderName(overrideCelebrity.trim()) || overrideCelebrity.trim();
    return {
      celebrityName: toTitleCase(cleanedOverride),
      moods: Array.from(moods).sort(),
      mediaType,
      fileName,
      ext,
    };
  }

  let folderParts = segs.slice(0, -1);
  if (folderParts.length >= 2) {
    const subParts = folderParts.slice(1);
    if (subParts.some((p) => !GENERIC_SUBFOLDERS.has(cleanFolderName(p).toLowerCase()))) {
      folderParts = subParts;
    }
  }

  let chosen = "";
  for (const part of folderParts) {
    const cleaned = cleanFolderName(part);
    const low = cleaned.toLowerCase();
    for (const w of low.match(/[a-z0-9]+/g) || []) {
      if (MOOD_KEYWORDS.has(w)) moods.add(w);
    }
    if (!cleaned || GENERIC_SUBFOLDERS.has(low) || MOOD_KEYWORDS.has(low) || low.length < 2) {
      continue;
    }
    if (!chosen) chosen = cleaned;
  }

  if (chosen) {
    return {
      celebrityName: toTitleCase(chosen),
      moods: Array.from(moods).sort(),
      mediaType,
      fileName,
      ext,
    };
  }

  const nameTokens = stemTokens.filter(
    (t) => !/^\d+$/.test(t) && !MOOD_KEYWORDS.has(t) && !["img", "pic", "photo", "clip", "vid", "video"].includes(t)
  );
  const fallbackName = nameTokens.slice(0, 4).join(" ").trim() || stem;
  return {
    celebrityName: toTitleCase(fallbackName),
    moods: Array.from(moods).sort(),
    mediaType,
    fileName,
    ext,
  };
}

export function buildInstantVaultIndex(validItems, overrideCelebrity = "", preference = "mix_both") {
  const grouped = new Map();
  const filesByRelKey = new Map();
  const filesByCelebrity = new Map();
  let topFolderName = "";

  for (let i = 0; i < validItems.length; i++) {
    const item = validItems[i];
    const file = item.file;
    const rawRel = item.relPath || file?.webkitRelativePath || file?.name || "";
    if (!topFolderName && rawRel.includes("/")) {
      topFolderName = rawRel.split("/")[0];
    } else if (!topFolderName && rawRel.includes("\\")) {
      topFolderName = rawRel.split("\\")[0];
    }
    const relKey = canonicalVaultRel(rawRel, overrideCelebrity);
    if (!relKey || !file) continue;

    const { celebrityName, moods, mediaType, fileName, ext } = parseCelebrityAndMood(rawRel, overrideCelebrity);
    filesByRelKey.set(relKey, file);

    const celebLow = celebrityName.toLowerCase();
    if (!filesByCelebrity.has(celebLow)) {
      filesByCelebrity.set(celebLow, []);
    }
    filesByCelebrity.get(celebLow).push({
      relKey,
      file,
      celebrity_name: celebrityName,
      media_type: mediaType,
      file_name: fileName,
      ext,
      mood_tags: moods,
    });

    let entry = grouped.get(celebrityName);
    if (!entry) {
      entry = {
        celebrity_name: celebrityName,
        image_count: 0,
        video_count: 0,
        total_count: 0,
        moodSet: new Set(),
        assets: [],
      };
      grouped.set(celebrityName, entry);
    }
    if (mediaType === "video") {
      entry.video_count += 1;
    } else {
      entry.image_count += 1;
    }
    entry.total_count += 1;
    for (const m of moods) entry.moodSet.add(m);

    if (entry.assets.length < 8) {
      entry.assets.push({
        id: `local:${relKey}`,
        relKey,
        celebrity_name: celebrityName,
        media_type: mediaType,
        file_name: fileName,
        ext,
        size: file.size || 0,
        mood_tags: moods,
        preview_url: "",
        is_local: true,
      });
    }
  }

  const celebrities = Array.from(grouped.values())
    .sort((a, b) => a.celebrity_name.localeCompare(b.celebrity_name))
    .map((c) => ({
      celebrity_name: c.celebrity_name,
      image_count: c.image_count,
      video_count: c.video_count,
      total_count: c.total_count,
      moods: Array.from(c.moodSet).sort(),
      assets: c.assets,
    }));

  return {
    index: {
      folder_path: topFolderName || overrideCelebrity || "Selected Celebrity Folder",
      preference: preference || "mix_both",
      total_assets: filesByRelKey.size,
      celebrities,
      updatedAt: Date.now(),
    },
    filesByRelKey,
    filesByCelebrity,
  };
}

export function mergeVaultLibraries(serverLib, localIndex) {
  if (!localIndex?.celebrities?.length) return serverLib;
  if (!serverLib?.celebrities?.length) {
    return localIndex;
  }

  const byName = new Map();
  for (const sc of serverLib.celebrities) {
    byName.set(sc.celebrity_name.toLowerCase(), {
      ...sc,
      assets: [...(sc.assets || [])],
    });
  }

  for (const lc of localIndex.celebrities) {
    const key = lc.celebrity_name.toLowerCase();
    const localAssets = lc.assets || [];
    const existing = byName.get(key);
    if (!existing) {
      byName.set(key, {
        ...lc,
        assets: localAssets,
      });
    } else {
      const seenFiles = new Set(existing.assets.map((a) => (a.file_name || "").toLowerCase()));
      for (const la of localAssets) {
        if (!seenFiles.has((la.file_name || "").toLowerCase()) && existing.assets.length < 8) {
          existing.assets.push(la);
        } else if (la.relKey) {
          const match = existing.assets.find((a) => (a.file_name || "").toLowerCase() === (la.file_name || "").toLowerCase());
          if (match && !match.relKey) match.relKey = la.relKey;
        }
      }
      existing.image_count = Math.max(existing.image_count || 0, lc.image_count || 0);
      existing.video_count = Math.max(existing.video_count || 0, lc.video_count || 0);
      existing.total_count = Math.max(existing.total_count || 0, lc.total_count || 0);
      existing.moods = Array.from(new Set([...(existing.moods || []), ...(lc.moods || [])])).sort();
    }
  }

  const mergedCelebrities = Array.from(byName.values()).sort((a, b) =>
    a.celebrity_name.localeCompare(b.celebrity_name)
  );
  const totalAssets = mergedCelebrities.reduce((sum, c) => sum + (c.total_count || 0), 0);

  return {
    folder_path: serverLib.folder_path || localIndex.folder_path || "",
    preference: serverLib.preference || localIndex.preference || "mix_both",
    total_assets: Math.max(serverLib.total_assets || 0, localIndex.total_assets || 0, totalAssets),
    celebrities: mergedCelebrities,
  };
}

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

export async function getCachedVaultManifest(workspaceKey) {
  try {
    const db = await openHandleDb();
    const record = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(`manifest_${workspaceKey || "default"}`);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return record?.files && typeof record.files === "object" ? record.files : {};
  } catch {
    return {};
  }
}

export async function saveCachedVaultManifest(workspaceKey, files) {
  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(
        { files: files || {}, updatedAt: Date.now() },
        `manifest_${workspaceKey || "default"}`
      );
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {}
}

export async function getLocalVaultIndex(workspaceKey) {
  try {
    const db = await openHandleDb();
    const record = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(`vault_index_${workspaceKey || "default"}`);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return record?.celebrities ? record : null;
  } catch {
    return null;
  }
}

export async function saveLocalVaultIndex(workspaceKey, indexData) {
  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(
        indexData,
        `vault_index_${workspaceKey || "default"}`
      );
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {}
}

export async function clearLocalVaultIndex(workspaceKey) {
  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(`vault_index_${workspaceKey || "default"}`);
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
          if (filePromises.length >= 128) {
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

  // Drain BFS directory queue with up to 12 concurrent directory scanners
  while (queue.length > 0) {
    if (signal?.aborted) throw new DOMException("Upload cancelled", "AbortError");
    const wave = queue.splice(0, 12);
    await Promise.all(wave.map((node) => processDir(node)));
  }
  if (onProgress) onProgress(items.length);
  return items;
}
