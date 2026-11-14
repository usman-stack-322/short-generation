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
    .replace(/[-_\s]*20\d{6}T\d{6}Z(?:[-_0-9]+)?$/i, "")
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

const NON_PERSON_WORDS = new Set([
  "clash", "clashes", "commentary", "analysis", "highlights", "highlight", "arena",
  "studio", "podcast", "podcasts", "show", "debate", "debates", "media", "discussion",
  "discussions", "court", "floor", "desk", "room", "basketball", "football", "baseball",
  "soccer", "boxing", "ufc", "nba", "wnba", "nfl", "mlb", "ncaa", "news", "report",
  "reports", "story", "history", "timeline", "moment", "moments", "scene", "clip",
  "clips", "video", "videos", "photo", "photos", "image", "images", "picture", "crowd",
  "fans", "panel", "host", "microphone", "microphones", "mic", "interview", "interviews",
  "conference", "press", "game", "games", "series", "finals", "season", "league",
  "championship", "trophy", "ring", "rings", "award", "awards", "ceremony", "hall",
  "fame", "star", "stars", "legend", "legends", "player", "players", "coach", "coaches",
  "team", "teams", "club", "city", "state", "street", "house", "building", "screen",
  "setup", "reaction", "reactions", "impact", "drama", "beef", "feud", "battle", "fight",
]);

const NICKNAME_ALIASES = {
  "nick young": ["swaggy p", "swaggyp"],
  "stephen curry": ["steph curry", "steph"],
  "lebron james": ["king james", "bron", "lebron"],
  "shaquille o neal": ["shaq", "shaquille oneal"],
  "shaquille oneal": ["shaq", "shaquille o neal"],
  "iman shumpert": ["shump", "shumpert"],
  "gilbert arenas": ["agent zero", "gils arena", "gil arenas"],
  "joe budden": ["budden"],
  "carmelo anthony": ["melo"],
  "charles barkley": ["chuck", "barkley"],
  "stephen a smith": ["stephen a", "stephen smith"],
  "shannon sharpe": ["unc", "shannon"],
  "kevin durant": ["kd"],
  "allen iverson": ["iverson"],
  "michael jordan": ["jordan"],
  "kobe bryant": ["kobe", "mamba"],
  "draymond green": ["draymond"],
  "kyrie irving": ["kyrie"],
  "giannis antetokounmpo": ["giannis"],
  "nikola jokic": ["jokic"],
  "luka doncic": ["luka"],
};

export function normVaultEntity(text) {
  let t = String(text || "");
  try {
    t = t.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  } catch {}
  t = t
    .replace(/[’‘]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/\$/g, "s")
    .replace(/\b([A-Za-z])\./g, "$1")
    .replace(/'s\b/gi, " ");
  return (t.toLowerCase().match(/[a-z0-9]+/g) || []).join(" ");
}

function hasNormPhrase(normHaystack, phrase) {
  if (!phrase || phrase.length < 3 || !normHaystack) return false;
  const padded = ` ${normHaystack} `;
  return padded.includes(` ${phrase} `);
}

function editSimilarity(a, b) {
  if (a === b) return 1;
  if (!a || !b) return 0;
  const la = a.length;
  const lb = b.length;
  if (Math.abs(la - lb) > 3) return 0;
  const dp = Array.from({ length: lb + 1 }, (_, j) => j);
  for (let i = 1; i <= la; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= lb; j++) {
      const temp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? prev : 1 + Math.min(prev, dp[j], dp[j - 1]);
      prev = temp;
    }
  }
  return 1 - dp[lb] / Math.max(la, lb);
}

function buildCelebVariants(celebName) {
  const base = normVaultEntity(celebName);
  if (!base || base.length < 3 || GENERIC_SUBFOLDERS.has(base)) return [];
  const variants = [base];
  const compact = normVaultEntity(String(celebName || "").replace(/([A-Za-z])['’]([A-Za-z])/g, "$1$2"));
  if (compact && !variants.includes(compact)) variants.push(compact);
  const tokens = base.split(" ");
  if (tokens.length >= 3 && tokens.slice(1, -1).some((t) => t.length === 1)) {
    const noMid = tokens.filter((t, idx) => !(idx > 0 && idx < tokens.length - 1 && t.length === 1)).join(" ");
    if (noMid && !variants.includes(noMid)) variants.push(noMid);
  }
  for (let i = 0; i < tokens.length - 1; i++) {
    if (tokens[i].length === 1 && tokens[i + 1].length >= 2) {
      const joined = [...tokens.slice(0, i), tokens[i] + tokens[i + 1], ...tokens.slice(i + 2)].join(" ");
      if (joined && !variants.includes(joined)) variants.push(joined);
    }
  }
  for (const v of [...variants]) {
    for (const alias of NICKNAME_ALIASES[v] || []) {
      const na = normVaultEntity(alias);
      if (na && !variants.includes(na)) variants.push(na);
    }
  }
  return variants;
}

export function matchCelebrityClipFromMap(byCeleb, scene, optionsOrPeople = [], legacyPreference = "mix_both", legacyUsedRels = new Set()) {
  if (!byCeleb || byCeleb.size === 0) return null;

  const opts = Array.isArray(optionsOrPeople)
    ? {
        people: optionsOrPeople,
        allScenes: [],
        draftTitle: "",
        preference: legacyPreference || "mix_both",
        usedRelKeys: legacyUsedRels || new Set(),
        usedCelebCounts: new Map(),
        lastMatchedCelebrity: "",
      }
    : {
        people: optionsOrPeople?.people || [],
        allScenes: optionsOrPeople?.allScenes || [],
        draftTitle: optionsOrPeople?.draftTitle || "",
        preference: optionsOrPeople?.preference || "mix_both",
        usedRelKeys: optionsOrPeople?.usedRelKeys || new Set(),
        usedCelebCounts: optionsOrPeople?.usedCelebCounts || new Map(),
        lastMatchedCelebrity: optionsOrPeople?.lastMatchedCelebrity || "",
      };

  const narrationNorm = normVaultEntity(scene?.narration || "");
  const visualNorm = normVaultEntity(
    [scene?.on_screen_text || "", scene?.visual_description || "", scene?.image_query || ""].join(" ")
  );
  const sceneNorm = `${narrationNorm} ${visualNorm}`.trim();
  const sceneTokens = new Set(sceneNorm.split(" ").filter(Boolean));

  const scriptParts = [
    opts.draftTitle || "",
    ...(opts.people || []),
    ...(opts.allScenes || []).map((s) =>
      [s?.narration || "", s?.on_screen_text || "", s?.visual_description || "", s?.image_query || ""].join(" ")
    ),
  ];
  const scriptNorm = normVaultEntity(scriptParts.join(" ")) || sceneNorm;
  const scriptTokens = new Set(scriptNorm.split(" ").filter(Boolean));

  const celebMeta = [];
  const surnameCounts = new Map();
  const firstnameCounts = new Map();

  for (const [celebKey, items] of byCeleb.entries()) {
    if (!items || !items.length) continue;
    const displayCeleb = items[0]?.celebrity_name || celebKey;
    const variants = buildCelebVariants(displayCeleb);
    if (!variants.length) continue;
    const normName = variants[0];
    const tokens = normName.split(" ").filter(Boolean);
    const firstname = tokens.length >= 2 && tokens[0].length >= 4 && !NON_PERSON_WORDS.has(tokens[0]) ? tokens[0] : "";
    const surname =
      tokens.length >= 2 && tokens[tokens.length - 1].length >= 4 && !NON_PERSON_WORDS.has(tokens[tokens.length - 1])
        ? tokens[tokens.length - 1]
        : "";
    if (firstname) firstnameCounts.set(firstname, (firstnameCounts.get(firstname) || 0) + 1);
    if (surname) surnameCounts.set(surname, (surnameCounts.get(surname) || 0) + 1);
    celebMeta.push({ celebKey, displayCeleb, normName, tokens, variants, firstname, surname, items });
  }

  function scoreCelebAgainstText(meta, primaryText, secondaryText, tokenSet) {
    for (const v of meta.variants) {
      if (hasNormPhrase(primaryText, v)) {
        const idx = primaryText.indexOf(v);
        const posBonus = idx >= 0 ? Math.max(0, 24 - Math.floor(idx / 10)) : 0;
        return 320 + posBonus;
      }
    }
    for (const v of meta.variants) {
      if (hasNormPhrase(secondaryText, v)) {
        return 270;
      }
    }
    if (meta.tokens.length >= 2 && meta.tokens.every((t) => tokenSet.has(t))) {
      return 240;
    }
    const uniqueSurname = meta.surname && (surnameCounts.get(meta.surname) === 1 || (meta.firstname && scriptTokens.has(meta.firstname)));
    const uniqueFirstname = meta.firstname && (firstnameCounts.get(meta.firstname) === 1 || (meta.surname && scriptTokens.has(meta.surname)));

    if (uniqueSurname && hasNormPhrase(primaryText, meta.surname)) return 220;
    if (uniqueFirstname && hasNormPhrase(primaryText, meta.firstname)) return 210;
    if (uniqueSurname && hasNormPhrase(secondaryText, meta.surname)) return 185;
    if (uniqueFirstname && hasNormPhrase(secondaryText, meta.firstname)) return 175;

    // Fuzzy token match for minor spelling differences (e.g. Reeves vs Reaves)
    if (meta.tokens.length >= 2) {
      const words = Array.from(tokenSet).filter((w) => w.length >= 4 && !NON_PERSON_WORDS.has(w));
      const firstHit = words.some((w) => editSimilarity(w, meta.tokens[0]) >= 0.84);
      const lastHit = words.some((w) => editSimilarity(w, meta.tokens[meta.tokens.length - 1]) >= 0.84);
      if (firstHit && lastHit) return 200;
    }
    return 0;
  }

  // Pass 1: Match celebrity mentioned directly in THIS scene's script/narration/visuals
  let matchedCelebs = [];
  for (const meta of celebMeta) {
    const sc = scoreCelebAgainstText(meta, narrationNorm, visualNorm, sceneTokens);
    if (sc > 0) {
      matchedCelebs.push({ meta, celebScore: sc });
    }
  }

  // Pass 2: If no celebrity in the vault matched this specific scene (or the scene's person is not in the folder),
  // fall back to the celebrity(s) from the overall Script / Title so we add another clip of that same person!
  if (matchedCelebs.length === 0) {
    const lastNorm = normVaultEntity(opts.lastMatchedCelebrity || "");
    for (const meta of celebMeta) {
      let sc = scoreCelebAgainstText(meta, scriptNorm, "", scriptTokens);
      if (sc <= 0 && lastNorm && meta.normName === lastNorm) {
        sc = 180;
      }
      if (sc > 0) {
        const sameAsLastBonus = lastNorm && meta.normName === lastNorm ? 25 : 0;
        matchedCelebs.push({ meta, celebScore: 150 + sameAsLastBonus });
      }
    }
  }

  if (matchedCelebs.length === 0) return null;

  const sceneNum = Number(scene?.number || 1);
  const pref = opts.preference || "mix_both";
  let bestItem = null;
  let bestScore = -Infinity;

  for (const { meta, celebScore } of matchedCelebs) {
    const priorUses = opts.usedCelebCounts.get(meta.celebKey) || 0;
    const adjustedCelebScore = celebScore - Math.min(45, priorUses * 14);

    for (let idx = 0; idx < meta.items.length; idx++) {
      const item = meta.items[idx];
      let score = adjustedCelebScore;

      if (pref === "prefer_images") {
        if (item.media_type === "image") score += 35;
      } else if (pref === "prefer_clips") {
        if (item.media_type === "video") score += 45;
      } else {
        // Default "mix_both": favor video clips of the person while still allowing images
        score += item.media_type === "video" ? 28 : 12;
      }

      // Mood & filename keyword alignment (bonus when found; when not found, still picks another clip of this person!)
      for (const m of item.mood_tags || []) {
        if (sceneTokens.has(m)) score += 25;
      }
      const stemWords = normVaultEntity(String(item.file_name || "").replace(/\.[^.]+$/, "")).split(" ");
      for (const sw of stemWords) {
        if (sw.length >= 4 && !meta.tokens.includes(sw) && sceneTokens.has(sw)) {
          score += 15;
        }
      }

      // Strongly prefer unused clips of this person, and if all clips were used, rotate cleanly instead of failing!
      if (!opts.usedRelKeys.has(item.relKey)) {
        score += 110;
      } else {
        score -= 35;
      }

      const fileSize = item.file?.size || 0;
      if (fileSize > 0 && fileSize <= 50 * 1024 * 1024) {
        score += 10;
      } else if (fileSize > 180 * 1024 * 1024) {
        score -= 30;
      }

      // Deterministic rotation tie-breaker so multiple scenes of the same person pick distinct clips
      const rotationTie = ((sceneNum * 37 + idx * 13) % Math.max(1, meta.items.length)) / Math.max(1, meta.items.length);
      score += rotationTie * 4;

      if (score > bestScore) {
        bestScore = score;
        bestItem = item;
      }
    }
  }

  return bestItem;
}
