import { useEffect, useState } from "react";
import { api, mediaUrl } from "../services/api";
import { useUploads } from "../context/UploadContext";
import { PageHeader, EmptyState } from "../components/Shell";
import { Button } from "../components/UI";
import {
  CheckCircle2,
  Film,
  FolderOpen,
  FolderSync,
  FolderUp,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
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
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
      collected.push({ file, relPath: prefix ? `${prefix}/${file.name}` : file.name });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {
        batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
        for (const child of batch) {
          await walk(child, prefix ? `${prefix}/${entry.name}` : entry.name);
        }
      } while (batch.length > 0);
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

  const supportsFolderPicker =
    typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
  const uploadActive = Boolean(
    vaultJob && ["scanning", "checking", "uploading", "indexing"].includes(vaultJob.phase)
  );

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

  async function connectFolder(e) {
    if (e) e.preventDefault();
    if (!folderPath.trim()) return;
    setBusy(true); setError(""); setStatus("");
    try {
      const res = await api("/assets/connect-folder", {
        method: "POST",
        body: JSON.stringify({ folder_path: folderPath.trim(), preference }),
      });
      setStatus(`Connected folder (${res.total_assets} assets across ${res.celebrities.length} celebrities).`);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
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
    const items = Array.from(fileList || []).map((file) => ({
      file,
      relPath: file.webkitRelativePath || file.name,
    }));
    if (items.length) uploadEntries(items);
  }

  async function rescanLibrary() {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const res = await api("/assets/rescan", {
        method: "POST",
        body: JSON.stringify({ preference }),
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
    if (!supportsFolderPicker) return;
    setError("");
    setStatus("");
    try {
      const handle = await window.showDirectoryPicker({
        id: "celebrity-vault",
        mode: "read",
      });
      await startVaultUploadFromHandle(handle, {
        celebrityName: bulkCelebrity,
        preference,
      });
    } catch (err) {
      if (err?.name !== "AbortError") {
        setError(err?.message || "Could not open folder picker.");
      }
    }
  }

  function formatVaultBytes(bytes) {
    if (!bytes || bytes <= 0) return "0 MB";
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  const filteredCelebrities = (library?.celebrities || [])
    .filter((c) => !query.trim() || c.celebrity_name.toLowerCase().includes(query.trim().toLowerCase()))
    .map((c) => ({
      ...c,
      assets: c.assets.filter((a) => mediaFilter === "all" || a.media_type === mediaFilter),
    }))
    .filter((c) => c.assets.length > 0);

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
            Instant local indexing: reads celebrity subfolders directly from disk without copying gigabytes of video files.
          </p>

          <div className="studio-card-footer">
            <Button type="submit" loading={busy} style={{ width: "100%" }}>
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
              One folder per person, named exactly like them — e.g. <code>LeBron James/</code>, <code>Prince Harry/</code>. Checks already-saved clips in seconds, uploads 6 batches in parallel, and keeps running when you change pages.
            </p>
            <div className="vault-upload-actions">
              {supportsFolderPicker && (
                <Button type="button" disabled={busy || uploadActive} onClick={pickMainFolderFast}>
                  <FolderUp size={15} />
                  <span>Select Main Folder</span>
                </Button>
              )}
              <label className={`button ${supportsFolderPicker ? "button-secondary" : "button-primary"}`} style={{ cursor: "pointer", margin: 0 }}>
                <FolderUp size={15} />
                <span>{supportsFolderPicker ? "Browse Folder" : "Upload Main Folder"}</span>
                <input
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  style={{ display: "none" }}
                  disabled={busy || uploadActive}
                  onChange={(e) => { uploadBulkFiles(e.target.files); e.target.value = ""; }}
                />
              </label>
              <label className="button button-secondary" style={{ cursor: "pointer", margin: 0 }}>
                <ImageIcon size={15} />
                <span>Upload Files</span>
                <input
                  type="file"
                  multiple
                  accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.mkv,.m4v"
                  style={{ display: "none" }}
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

      {library?.folder_path && (
        <div className="vault-status-strip">
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="vault-folder-pill">
              <FolderOpen size={14} />
              <span>{library.folder_path}</span>
            </span>
            <span className="count-chip">{library.total_assets} assets</span>
            <span className="vault-helper-text">{library.celebrities.length} celebrities indexed (showing up to 12 previews each)</span>
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

      {!library ? (
        <p role="status">Loading celebrity library…</p>
      ) : filteredCelebrities.length === 0 ? (
        <EmptyState
          title="No celebrity assets indexed yet"
          detail="Connect your main folder path or click Upload Main Folder above."
        />
      ) : (
        <div style={{ display: "grid", gap: 20 }}>
          {filteredCelebrities.map((celeb) => (
            <section key={celeb.celebrity_name} className="studio-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>{celeb.celebrity_name}</h3>
                <div style={{ display: "flex", gap: 10, fontSize: 12.5, color: "#64748b", fontWeight: 600 }}>
                  <span><ImageIcon size={14} style={{ verticalAlign: "middle" }} /> {celeb.image_count} images</span>
                  <span><Film size={14} style={{ verticalAlign: "middle" }} /> {celeb.video_count} clips</span>
                </div>
              </div>
              <div className="vault-media-grid">
                {celeb.assets.map((asset) => (
                  <div key={asset.id} className="vault-asset-card">
                    <div className="vault-media-thumb">
                      {asset.media_type === "video" ? (
                        <>
                          <video
                            src={mediaUrl(asset.preview_url)}
                            muted
                            loop
                            playsInline
                            preload="none"
                            onMouseEnter={(e) => e.currentTarget.play().catch(() => {})}
                            onMouseLeave={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                          />
                          <span className="vault-duration-badge">
                            {asset.duration ? `${asset.duration.toFixed(1)}s` : "CLIP"}
                          </span>
                        </>
                      ) : (
                        <img src={mediaUrl(asset.preview_url)} alt={asset.file_name} loading="lazy" />
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
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
