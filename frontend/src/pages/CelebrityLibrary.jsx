import { useEffect, useMemo, useRef, useState } from "react";
import { api, mediaUrl } from "../services/api";
import { rescanVaultWithFallback, useUploads } from "../context/UploadContext";
import { mergeVaultLibraries } from "../utils/folderStore";
import { PageHeader, EmptyState } from "../components/Shell";
import { Button } from "../components/UI";
import {
  ArrowUp,
  CheckCircle2,
  Film,
  FolderOpen,
  FolderSync,
  FolderUp,
  HardDrive,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
  XCircle,
} from "lucide-react";

async function collectDroppedFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []);
  const entries = items.map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length) {
    return Array.from(dataTransfer?.files || []).map((file) => ({ file, relPath: file.webkitRelativePath || file.name }));
  }
  const collected = [];
  async function walk(entry, prefix = "") {
    if (entry.isFile) {
      try {
        const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
        if (file && file.size > 0 && !file.name.startsWith(".tmp_")) {
          collected.push({ file, relPath: prefix ? `${prefix}/${file.name}` : file.name });
        }
      } catch {}
    } else if (entry.isDirectory) {
      const low = (entry.name || "").toLowerCase();
      if (entry.name.startsWith(".tmp_") || entry.name.startsWith("$") || low === "system volume information") {
        return;
      }
      const reader = entry.createReader();
      let batch;
      try {
        do {
          batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
          for (const child of batch) {
            await walk(child, prefix ? `${prefix}/${entry.name}` : entry.name);
          }
        } while (batch.length > 0);
      } catch {}
    }
  }
  for (const entry of entries) {
    await walk(entry, "");
  }
  return collected;
}

export default function CelebrityLibrary() {
  const {
    vaultJob,
    vaultVersion,
    savedFolder,
    forgetSavedFolder,
    localVaultIndex,
    getLocalPreviewUrl,
    startVaultUpload,
    startVaultUploadFromHandle,
    cancelVaultUpload,
  } = useUploads();
  const [library, setLibrary] = useState(null);
  const [folderPath, setFolderPath] = useState("");
  const [preference, setPreference] = useState("mix_both");
  const [bulkCelebrity, setBulkCelebrity] = useState("");
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [mediaFilter, setMediaFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [canBrowseLocal, setCanBrowseLocal] = useState(false);
  const [pcBrowserOpen, setPcBrowserOpen] = useState(false);
  const [pcBrowserData, setPcBrowserData] = useState(null);
  const [pcBrowserLoading, setPcBrowserLoading] = useState(false);
  const [pcBrowserError, setPcBrowserError] = useState("");
  const [visibleCelebCount, setVisibleCelebCount] = useState(12);
  const [activeVideoId, setActiveVideoId] = useState(null);
  const folderInputRef = useRef(null);

  const supportsFolderPicker =
    typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
  const uploadActive = Boolean(
    vaultJob && ["scanning", "checking", "uploading", "indexing"].includes(vaultJob.phase)
  );

  function setFolderInputNode(el) {
    folderInputRef.current = el;
    if (!el) return;
    el.webkitdirectory = true;
    el.directory = true;
    el.mozdirectory = true;
    el.setAttribute("webkitdirectory", "");
    el.setAttribute("directory", "");
  }

  useEffect(() => {
    setFolderInputNode(folderInputRef.current);
  }, []);

  async function load() {
    try {
      const data = await api("/assets/library");
      setLibrary(data);
      if (data.folder_path && !folderPath) setFolderPath(data.folder_path);
      if (data.preference) setPreference(data.preference);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, [vaultVersion]);

  useEffect(() => {
    if (!localStorage.getItem("token")) return;
    api("/assets/local-browse")
      .then(() => setCanBrowseLocal(true))
      .catch(() => setCanBrowseLocal(false));
  }, []);

  async function openPcBrowser(targetPath = "") {
    setPcBrowserOpen(true);
    setPcBrowserLoading(true);
    setPcBrowserError("");
    try {
      const qs = targetPath ? `?path=${encodeURIComponent(targetPath)}` : "";
      const data = await api(`/assets/local-browse${qs}`);
      setPcBrowserData(data);
    } catch (err) {
      setPcBrowserError(err?.message || "Could not inspect local disk folders.");
    } finally {
      setPcBrowserLoading(false);
    }
  }

  async function connectPickedLocalFolder(selectedPath) {
    const clean = (selectedPath || "").trim();
    if (!clean) return;
    setFolderPath(clean);
    setPcBrowserOpen(false);
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const res = await api("/assets/connect-folder", {
        method: "POST",
        body: JSON.stringify({ folder_path: clean, preference }),
      });
      setStatus(`Saved & indexed ${res.total_assets.toLocaleString()} assets across ${res.celebrities.length} celebrities — ready for permanent reuse.`);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function connectFolder(e) {
    if (e) e.preventDefault();
    if (!folderPath.trim()) return;
    await connectPickedLocalFolder(folderPath);
  }

  function uploadEntries(rawItems) {
    setError("");
    setStatus("");
    startVaultUpload({
      rawItems,
      celebrityName: bulkCelebrity,
      preference,
    });
  }

  function uploadBulkFiles(fileList) {
    setError("");
    const items = Array.from(fileList || []).map((file) => ({
      file,
      relPath: file.webkitRelativePath || file.name,
    }));
    if (!items.length) {
      setStatus("No readable files were returned from that folder. Choose a folder containing images or video clips.");
      return;
    }
    uploadEntries(items);
  }

  async function rescanLibrary() {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const res = await rescanVaultWithFallback({
        preference,
        fallbackFolderPath: (library?.folder_path || folderPath || "").trim(),
        throwOnMissingFallback: true,
      });
      setStatus(`Library rescanned (${res.total_assets} assets across ${res.celebrities.length} celebrities).`);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function pickMainFolderFast() {
    setError("");
    setStatus("");
    if (!supportsFolderPicker) {
      folderInputRef.current?.click();
      return;
    }
    const openedAt = Date.now();
    try {
      const handle = await window.showDirectoryPicker({
        mode: "read",
      });
      await startVaultUploadFromHandle(handle, {
        celebrityName: bulkCelebrity,
        preference,
        skipPermissionCheck: true,
      });
    } catch (err) {
      const elapsed = Date.now() - openedAt;
      if (err?.name === "AbortError" && elapsed >= 400) {
        setStatus("If Windows blocked Desktop, Downloads, or a drive root here, click Select Main Folder instead — it works on every folder.");
        return;
      }
      if (
        err?.name === "SecurityError" ||
        err?.name === "NotAllowedError" ||
        err?.name === "TypeError" ||
        (err?.name === "AbortError" && elapsed < 400)
      ) {
        setStatus("Direct quick-handle picker isn't allowed here. Click the primary Select Main Folder button — it works on all folders.");
        return;
      }
      setError(err?.message || "Could not open quick folder sync. Click Select Main Folder instead.");
    }
  }

  function formatVaultBytes(bytes) {
    if (!bytes || bytes <= 0) return "0 MB";
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    if (bytes < 1024 * 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    return `${(bytes / (1024 * 1024 * 1024 * 1024)).toFixed(2)} TB`;
  }

  const effectiveLibrary = useMemo(
    () => mergeVaultLibraries(library, localVaultIndex),
    [library, localVaultIndex]
  );

  const filteredCelebrities = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (effectiveLibrary?.celebrities || [])
      .filter((c) => !q || c.celebrity_name.toLowerCase().includes(q))
      .map((c) => ({
        ...c,
        assets: c.assets.filter((a) => mediaFilter === "all" || a.media_type === mediaFilter),
      }))
      .filter((c) => c.assets.length > 0 || (mediaFilter === "all" && c.total_count > 0));
  }, [effectiveLibrary, query, mediaFilter]);

  const displayedCelebrities = filteredCelebrities.slice(0, visibleCelebCount);

  const livePct =
    vaultJob?.phase === "checking" && vaultJob?.totalFiles > 0
      ? Math.min(100, Math.round(((vaultJob.checkedFiles || 0) / vaultJob.totalFiles) * 100))
      : vaultJob?.totalBytes > 0
      ? Math.min(100, Math.round(((vaultJob.loadedBytes || 0) / vaultJob.totalBytes) * 100))
      : vaultJob?.phase === "done"
      ? 100
      : 0;

  return (
    <div className="celebrity-vault-page">
      <PageHeader
        eyebrow="PEOPLE & CLIPS"
        title="Celebrity Folder Library"
        description="Connect a main directory of celebrity subfolders or sync your folder once — only missing clips are uploaded, even while you browse other pages."
      />

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {status && <div className="notice notice-success" role="status">{status}</div>}

      <div className="vault-top-grid">
        <form className="studio-card" onSubmit={connectFolder}>
          <div className="studio-card-head">
            <h3 className="studio-card-title" style={{ margin: 0 }}>
              <FolderOpen size={18} />
              <span>Connect Local Folder Path</span>
            </h3>
          </div>

          <div className="studio-field">
            <label className="studio-label" htmlFor="vault-folder-path">Main Parent Directory Path</label>
            <div className="studio-input-icon-wrap">
              <span className="studio-input-icon"><FolderOpen size={16} /></span>
              <input
                id="vault-folder-path"
                className="studio-mono-input"
                required
                placeholder="D:\data video or C:\celebrity_vault"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
              />
            </div>
          </div>

          <div className="studio-field">
            <label className="studio-label" htmlFor="vault-preference">Scene Matching Preference</label>
            <select
              id="vault-preference"
              value={preference}
              onChange={(e) => setPreference(e.target.value)}
            >
              <option value="mix_both">Mix Both (Images + Short Clips)</option>
              <option value="prefer_clips">Prefer Video Clips (.mp4 / .mov / .webm)</option>
              <option value="prefer_images">Prefer Images (.jpg / .png / .webp)</option>
            </select>
          </div>

          <p className="vault-helper-text" style={{ marginBottom: 14 }}>
            Best for 100 GB – 1 TB+ local folders: scans directly on disk in seconds with zero file copying and stays saved permanently.
          </p>

          <div className="studio-card-footer" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {canBrowseLocal && (
              <Button
                type="button"
                variant="secondary"
                disabled={busy || uploadActive}
                onClick={() => openPcBrowser(folderPath.trim())}
                style={{ flex: "1 1 150px" }}
              >
                <HardDrive size={15} />
                <span>Browse This PC</span>
              </Button>
            )}
            <Button type="submit" loading={busy} style={{ flex: "2 1 190px" }}>
              <span>Scan &amp; Connect Folder</span>
            </Button>
          </div>
        </form>

        <div className="studio-card">
          <div className="studio-card-head">
            <h3 className="studio-card-title" style={{ margin: 0 }}>
              <Upload size={18} />
              <span>People &amp; Clips Sync</span>
            </h3>
          </div>

          {canBrowseLocal && (
            <div className="vault-saved-bar" style={{ marginBottom: 12 }}>
              <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                100 GB+ folder on this PC? Link directly in ~2s with zero copying:
              </span>
              <Button
                type="button"
                variant="secondary"
                disabled={busy || uploadActive}
                onClick={() => openPcBrowser("")}
              >
                <HardDrive size={14} />
                <span>Browse This PC (Instant)</span>
              </Button>
            </div>
          )}

          {savedFolder?.handle && (
            <div className="vault-saved-bar">
              <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <FolderSync size={16} />
                <span style={{ fontWeight: 600, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  Saved folder: {savedFolder.name}
                  {savedFolder.totalFound ? ` (${savedFolder.totalFound.toLocaleString()} clips)` : ""}
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                <Button
                  type="button"
                  disabled={busy || uploadActive}
                  onClick={() =>
                    startVaultUploadFromHandle(savedFolder.handle, {
                      celebrityName: bulkCelebrity,
                      preference,
                    })
                  }
                >
                  <RefreshCw size={14} />
                  <span>Quick Re-Sync</span>
                </Button>
                <button
                  type="button"
                  className="button button-secondary"
                  title="Forget saved folder"
                  disabled={uploadActive}
                  onClick={forgetSavedFolder}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          )}

          {!savedFolder?.handle && effectiveLibrary?.total_assets > 0 && (
            <div className="vault-saved-bar" style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <CheckCircle2 size={16} color="#16a34a" />
                <span style={{ fontWeight: 600, fontSize: 13 }}>
                  Saved in workspace: {effectiveLibrary.total_assets.toLocaleString()} clips across {effectiveLibrary.celebrities.length} celebrities (reused automatically in Create Short).
                </span>
              </div>
            </div>
          )}

          <div className="studio-field">
            <label className="studio-label" htmlFor="vault-celeb-name">Celebrity Name (leave blank when uploading a Main Folder)</label>
            <input
              id="vault-celeb-name"
              placeholder="Leave blank if uploading MainFolder/CelebrityName/..."
              value={bulkCelebrity}
              onChange={(e) => setBulkCelebrity(e.target.value)}
            />
          </div>

          <div
            className={`vault-dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={async (e) => {
              e.preventDefault();
              setDragging(false);
              const items = await collectDroppedFiles(e.dataTransfer);
              if (items.length) uploadEntries(items);
            }}
          >
            <p className="vault-helper-text">
              One folder per person, named exactly like them — e.g. <code>LeBron James/</code>, <code>Prince Harry/</code>. Checks already-saved clips in seconds, streams large videos in chunks, and keeps running when you change pages.
            </p>
            <div className="vault-upload-actions">
              <label
                className="button button-primary"
                style={{
                  cursor: busy || uploadActive ? "not-allowed" : "pointer",
                  margin: 0,
                  opacity: busy || uploadActive ? 0.6 : 1,
                  pointerEvents: busy || uploadActive ? "none" : "auto",
                }}
              >
                <FolderUp size={15} />
                <span>Select Main Folder</span>
                <input
                  ref={setFolderInputNode}
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  style={{ position: "fixed", left: "-9999px", width: 1, height: 1, opacity: 0 }}
                  disabled={busy || uploadActive}
                  onChange={(e) => { uploadBulkFiles(e.target.files); e.target.value = ""; }}
                />
              </label>
              {supportsFolderPicker && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={busy || uploadActive}
                  onClick={pickMainFolderFast}
                  title="Optional Chrome handle sync for quick 1-click re-sync of non-system folders"
                >
                  <FolderSync size={15} />
                  <span>Auto-Sync Folder</span>
                </Button>
              )}
              <label
                className="button button-secondary"
                style={{
                  cursor: busy || uploadActive ? "not-allowed" : "pointer",
                  margin: 0,
                  opacity: busy || uploadActive ? 0.6 : 1,
                  pointerEvents: busy || uploadActive ? "none" : "auto",
                }}
              >
                <ImageIcon size={15} />
                <span>Upload Files</span>
                <input
                  type="file"
                  multiple
                  accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.mkv,.m4v"
                  style={{ position: "fixed", left: "-9999px", width: 1, height: 1, opacity: 0 }}
                  disabled={busy || uploadActive}
                  onChange={(e) => { uploadBulkFiles(e.target.files); e.target.value = ""; }}
                />
              </label>
            </div>
          </div>

          {vaultJob && (
            <div className={`vault-live-progress ${vaultJob.phase}`}>
              <div className="vault-live-top">
                <div className="vault-live-label">
                  {uploadActive && <Loader2 size={16} className="spin" />}
                  {vaultJob.phase === "done" && <CheckCircle2 size={16} color="#16a34a" />}
                  {(vaultJob.phase === "error" || vaultJob.phase === "cancelled") && <XCircle size={16} color="#dc2626" />}
                  <strong>
                    {vaultJob.phase === "scanning"
                      ? `Scanning folder… ${(vaultJob.checkedFiles || 0).toLocaleString()} clips found`
                      : vaultJob.phase === "checking"
                      ? `Checking clips ${(vaultJob.checkedFiles || 0).toLocaleString()}/${(vaultJob.totalFiles || 0).toLocaleString()}`
                      : vaultJob.phase === "uploading"
                      ? `Uploading clips ${(vaultJob.uploadedFiles || 0).toLocaleString()}/${(vaultJob.newFilesTotal || vaultJob.totalFiles || 0).toLocaleString()}`
                      : vaultJob.message}
                  </strong>
                </div>
                {uploadActive && (
                  <button type="button" className="global-upload-action" onClick={cancelVaultUpload}>
                    Stop
                  </button>
                )}
              </div>
              {uploadActive && (vaultJob.phase === "checking" || vaultJob.phase === "uploading") && (
                <>
                  <div className="global-upload-bar" style={{ marginTop: 8 }}>
                    <div className="global-upload-bar-fill" style={{ width: `${livePct}%` }} />
                  </div>
                  <div className="global-upload-meta" style={{ marginTop: 6 }}>
                    <span>
                      {livePct}%
                      {vaultJob.skippedFiles > 0 ? ` · ${vaultJob.skippedFiles.toLocaleString()} already saved` : ""}
                    </span>
                    {vaultJob.phase === "uploading" && vaultJob.totalBytes > 0 && (
                      <span>
                        {formatVaultBytes(vaultJob.loadedBytes)} / {formatVaultBytes(vaultJob.totalBytes)}
                        {vaultJob.speedBps > 0 ? ` · ${formatVaultBytes(vaultJob.speedBps)}/s` : ""}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {effectiveLibrary?.folder_path && (
        <div className="vault-status-strip">
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="vault-folder-pill">
              <FolderOpen size={14} />
              <span>{effectiveLibrary.folder_path}</span>
            </span>
            <span className="count-chip">{effectiveLibrary.total_assets.toLocaleString()} assets</span>
            <span className="vault-helper-text">{effectiveLibrary.celebrities.length} celebrities indexed (showing up to 16 previews each)</span>
          </div>
          <Button variant="secondary" disabled={busy || uploadActive} onClick={rescanLibrary}>
            <RefreshCw size={14} />
            <span>Rescan</span>
          </Button>
        </div>
      )}

      <div className="vault-filter-bar">
        <div className="vault-search-wrap studio-input-icon-wrap">
          <span className="studio-input-icon"><Search size={15} /></span>
          <input
            aria-label="Filter celebrities"
            style={{ paddingLeft: 36 }}
            placeholder="Search celebrities (e.g. Stephen A Smith)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="vault-pill-group">
          {[
            ["all", "All Celebrities"],
            ["image", "Images Only"],
            ["video", "Video Clips Only"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`filter-pill ${mediaFilter === key ? "active" : ""}`}
              onClick={() => setMediaFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {!effectiveLibrary ? (
        <p role="status">Loading celebrity library…</p>
      ) : filteredCelebrities.length === 0 ? (
        <EmptyState
          title="No celebrity assets indexed yet"
          detail="Connect your main folder path or click Select Main Folder above."
        />
      ) : (
        <div style={{ display: "grid", gap: 20 }}>
          {displayedCelebrities.map((celeb) => (
            <section key={celeb.celebrity_name} className="studio-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>{celeb.celebrity_name}</h3>
                <div style={{ display: "flex", gap: 10, fontSize: 12.5, color: "#64748b", fontWeight: 600 }}>
                  <span><ImageIcon size={14} style={{ verticalAlign: "middle" }} /> {celeb.image_count} images</span>
                  <span><Film size={14} style={{ verticalAlign: "middle" }} /> {celeb.video_count} clips</span>
                </div>
              </div>
              <div className="vault-media-grid">
                {celeb.assets.slice(0, 6).map((asset) => {
                  const isVideoActive = asset.media_type === "video" && activeVideoId === asset.id;
                  const rawUrl =
                    asset.media_type === "image" || isVideoActive
                      ? asset.preview_url || (asset.relKey ? getLocalPreviewUrl(asset.relKey) : "")
                      : "";
                  const previewSrc = mediaUrl(rawUrl);
                  return (
                  <div key={asset.id} className="vault-asset-card">
                    <div className="vault-media-thumb">
                      {asset.media_type === "video" ? (
                        isVideoActive && previewSrc ? (
                          <>
                            <video
                              src={previewSrc}
                              controls
                              autoPlay
                              muted
                              loop
                              playsInline
                              preload="metadata"
                            />
                            <span className="vault-duration-badge">
                              {asset.duration ? `${asset.duration.toFixed(1)}s` : "CLIP"}
                            </span>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setActiveVideoId(asset.id)}
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "center",
                              justifyContent: "center",
                              width: "100%",
                              height: "100%",
                              gap: 6,
                              color: "#475569",
                              background: "transparent",
                              border: "none",
                              cursor: "pointer",
                              fontSize: 12,
                              fontWeight: 600,
                            }}
                          >
                            <Film size={22} />
                            <span>{asset.relKey || asset.preview_url ? "Click to preview clip" : "Indexed video"}</span>
                            <span className="vault-duration-badge">
                              {asset.duration ? `${asset.duration.toFixed(1)}s` : "CLIP"}
                            </span>
                          </button>
                        )
                      ) : !previewSrc ? (
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 6, color: "#64748b", fontSize: 12 }}>
                          <ImageIcon size={22} />
                          <span>Indexed image</span>
                        </div>
                      ) : (
                        <img src={previewSrc} alt={asset.file_name} loading="lazy" />
                      )}
                    </div>
                    <div className="vault-asset-meta">
                      <strong title={asset.file_name}>{asset.file_name}</strong>
                      <div className="vault-mood-row">
                        <span className="mood-tag">{asset.media_type}</span>
                        {asset.mood_tags?.map((m) => (
                          <span key={m} className="mood-tag">{m}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
                })}
              </div>
            </section>
          ))}
          {filteredCelebrities.length > visibleCelebCount && (
            <div style={{ display: "flex", justifyContent: "center", paddingTop: 4 }}>
              <Button
                variant="secondary"
                onClick={() => setVisibleCelebCount((c) => c + 24)}
              >
                Show More Celebrities ({visibleCelebCount} of {filteredCelebrities.length})
              </Button>
            </div>
          )}
        </div>
      )}
      {pcBrowserOpen && (
        <div
          className="studio-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Browse Local PC Folder"
          onClick={() => setPcBrowserOpen(false)}
        >
          <div className="studio-modal" style={{ width: "min(640px, 100%)" }} onClick={(e) => e.stopPropagation()}>
            <div className="studio-modal-header">
              <div>
                <h3 style={{ margin: 0, fontSize: 17 }}>Select Local Celebrity Folder</h3>
                <p className="vault-helper-text" style={{ marginTop: 4 }}>
                  Pick your main folder once — scans 100 GB+ directly from disk with zero copying and saves permanently.
                </p>
              </div>
              <button
                type="button"
                className="button button-secondary"
                style={{ minHeight: 34, padding: "0 10px" }}
                onClick={() => setPcBrowserOpen(false)}
              >
                <X size={16} />
              </button>
            </div>

            {pcBrowserError && <div className="notice notice-error" role="alert">{pcBrowserError}</div>}

            {pcBrowserData?.shortcuts?.length > 0 && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {pcBrowserData.shortcuts.map((s) => (
                  <button
                    key={s.path}
                    type="button"
                    className={`filter-pill ${pcBrowserData.current_path === s.path ? "active" : ""}`}
                    onClick={() => openPcBrowser(s.path)}
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
              {pcBrowserData?.current_path && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={pcBrowserLoading}
                  onClick={() => openPcBrowser(pcBrowserData.parent_path || "")}
                >
                  <ArrowUp size={14} />
                  <span>Up</span>
                </Button>
              )}
              <div
                style={{
                  flex: 1,
                  minWidth: 200,
                  padding: "8px 12px",
                  borderRadius: 10,
                  border: "1px solid var(--edge-e6e8ef, #e2e8f0)",
                  background: "var(--bg-f8f8fb, #f8fafc)",
                  fontFamily: "monospace",
                  fontSize: 12.5,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={pcBrowserData?.current_path || "This PC"}
              >
                {pcBrowserData?.current_path || "This PC (Choose a Drive or Shortcut)"}
              </div>
            </div>

            <div
              style={{
                border: "1px solid var(--edge-e6e8ef, #e2e8f0)",
                borderRadius: 12,
                maxHeight: 300,
                overflowY: "auto",
                marginBottom: 14,
              }}
            >
              {pcBrowserLoading ? (
                <p style={{ padding: 18, margin: 0, textAlign: "center", color: "#64748b" }}>
                  Loading folders…
                </p>
              ) : !pcBrowserData?.folders?.length ? (
                <p style={{ padding: 18, margin: 0, textAlign: "center", color: "#64748b", fontSize: 13 }}>
                  No subfolders inside this directory
                  {pcBrowserData?.direct_media_count ? ` (${pcBrowserData.direct_media_count} media files found directly here)` : "."}
                </p>
              ) : (
                pcBrowserData.folders.map((f) => (
                  <button
                    key={f.path}
                    type="button"
                    onClick={() => openPcBrowser(f.path)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      width: "100%",
                      textAlign: "left",
                      padding: "10px 14px",
                      border: "none",
                      borderBottom: "1px solid var(--edge-e6e8ef, #e2e8f0)",
                      background: "transparent",
                      color: "inherit",
                      cursor: "pointer",
                      fontSize: 13.5,
                      fontWeight: 500,
                    }}
                  >
                    <FolderOpen size={16} color="#4f46e5" />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                  </button>
                ))
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="vault-helper-text">
                {pcBrowserData?.current_path
                  ? `${pcBrowserData.folders?.length || 0} subfolder(s)${pcBrowserData.direct_media_count ? ` · ${pcBrowserData.direct_media_count} direct clips` : ""}`
                  : "Open any drive or Desktop/Downloads folder to connect."}
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <Button type="button" variant="secondary" onClick={() => setPcBrowserOpen(false)}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  disabled={!pcBrowserData?.current_path || pcBrowserLoading || busy}
                  onClick={() => connectPickedLocalFolder(pcBrowserData.current_path)}
                >
                  <CheckCircle2 size={15} />
                  <span>Connect &amp; Save This Folder</span>
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
