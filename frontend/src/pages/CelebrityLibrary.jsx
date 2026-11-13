import { useEffect, useState } from "react";
import { api, mediaUrl } from "../services/api";
import { PageHeader, EmptyState } from "../components/Shell";
import { Button } from "../components/UI";
import { Film, FolderOpen, FolderUp, Image as ImageIcon, Lock, RefreshCw, Search, Upload } from "lucide-react";

const ALLOWED_EXT_RE = /\.(jpg|jpeg|png|webp|mp4|mov|webm|mkv|m4v)$/i;

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
  const [library, setLibrary] = useState(null);
  const [folderPath, setFolderPath] = useState("");
  const [preference, setPreference] = useState("mix_both");
  const [bulkCelebrity, setBulkCelebrity] = useState("");
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [mediaFilter, setMediaFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [progressText, setProgressText] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

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

  useEffect(() => { load(); }, []);

  async function connectFolder(e) {
    if (e) e.preventDefault();
    if (!folderPath.trim()) return;
    setBusy(true); setError(""); setStatus(""); setProgressText("Scanning local directory…");
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
      setProgressText("");
    }
  }

  async function uploadEntries(rawItems) {
    const valid = (rawItems || []).filter(({ file, relPath }) => {
      const name = relPath || file.name || "";
      return ALLOWED_EXT_RE.test(name) && file.size > 0;
    });
    if (!valid.length) {
      setError("No supported image (.jpg/.png/.webp) or video (.mp4/.mov/.webm) files found.");
      return;
    }

    // Group into batches of max 8 files or 50 MB so huge folders never time out
    const batches = [];
    let current = [];
    let currentBytes = 0;
    const MAX_BATCH_BYTES = 50 * 1024 * 1024;
    const MAX_BATCH_FILES = 8;

    for (const item of valid) {
      if (current.length >= MAX_BATCH_FILES || (current.length > 0 && currentBytes + item.file.size > MAX_BATCH_BYTES)) {
        batches.push(current);
        current = [];
        currentBytes = 0;
      }
      current.push(item);
      currentBytes += item.file.size;
    }
    if (current.length) batches.push(current);

    setBusy(true); setError(""); setStatus("");
    let uploadedCount = 0;
    let lastRes = null;

    try {
      for (let i = 0; i < batches.length; i++) {
        const batch = batches[i];
        const isLast = i === batches.length - 1;
        setProgressText(`Uploading batch ${i + 1} of ${batches.length} (${uploadedCount}/${valid.length} files)…`);
        const fd = new FormData();
        fd.append("celebrity_name", bulkCelebrity);
        fd.append("skip_scan", isLast ? "false" : "true");
        for (const { file, relPath } of batch) {
          fd.append("files", file, relPath || file.webkitRelativePath || file.name);
        }
        lastRes = await api("/assets/upload-bulk", { method: "POST", body: fd });
        uploadedCount += batch.length;
      }
      if (lastRes) {
        setStatus(`Uploaded ${uploadedCount} files & indexed ${lastRes.total_assets} total assets across ${lastRes.celebrities.length} celebrities.`);
      }
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      setProgressText("");
    }
  }

  function uploadBulkFiles(fileList) {
    const items = Array.from(fileList || []).map((file) => ({
      file,
      relPath: file.webkitRelativePath || file.name,
    }));
    uploadEntries(items);
  }

  const filteredCelebrities = (library?.celebrities || [])
    .filter((c) => !query.trim() || c.celebrity_name.toLowerCase().includes(query.trim().toLowerCase()))
    .map((c) => ({
      ...c,
      assets: c.assets.filter((a) => mediaFilter === "all" || a.media_type === mediaFilter),
    }))
    .filter((c) => c.assets.length > 0);

  const isAdmin = ["OWNER", "ADMIN"].includes(localStorage.getItem("role"));
  return (
    <div className="celebrity-vault-page">
      <PageHeader
        eyebrow="CELEBRITY VAULT"
        title="Celebrity Folder Library"
        description="Connect a main directory of celebrity subfolders or browse the shared workspace celebrity clips and photos below."
        action={!isAdmin && (
          <span className="studio-lock-pill">
            <Lock size={12} />
            <span>View &amp; Use Only (Uploads Managed by Owner)</span>
          </span>
        )}
      />

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {progressText && <div className="notice notice-info" role="status">{progressText}</div>}
      {status && <div className="notice notice-success" role="status">{status}</div>}

      <div className="vault-top-grid">
        <form className="studio-card" onSubmit={connectFolder}>
          <div className="studio-card-head">
            <h3 className="studio-card-title" style={{ margin: 0 }}>
              <FolderOpen size={18} />
              <span>Connect Local Folder Path</span>
            </h3>
            {!isAdmin && <span className="studio-lock-pill"><Lock size={12} /> Owner Only</span>}
          </div>

          <div className="studio-field">
            <label className="studio-label" htmlFor="vault-folder-path">Main Parent Directory Path</label>
            <div className="studio-input-icon-wrap">
              <span className="studio-input-icon"><FolderOpen size={16} /></span>
              <input
                id="vault-folder-path"
                className="studio-mono-input"
                required
                disabled={!isAdmin}
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
              disabled={!isAdmin}
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
            <Button type="submit" loading={busy} disabled={!isAdmin} style={{ width: "100%" }}>
              {!isAdmin && <Lock size={14} />}
              <span>{isAdmin ? "Scan & Connect Folder" : "Folder Connection Locked (Owner/Admin)"}</span>
            </Button>
          </div>
        </form>

        <div className="studio-card">
          <div className="studio-card-head">
            <h3 className="studio-card-title" style={{ margin: 0 }}>
              <Upload size={18} />
              <span>Bulk Upload Celebrity Files</span>
            </h3>
            {!isAdmin && <span className="studio-lock-pill"><Lock size={12} /> Owner Only</span>}
          </div>

          <div className="studio-field">
            <label className="studio-label" htmlFor="vault-celeb-name">Celebrity Name (leave blank when uploading a Main Folder)</label>
            <input
              id="vault-celeb-name"
              disabled={!isAdmin}
              placeholder="Leave blank if uploading MainFolder/CelebrityName/..."
              value={bulkCelebrity}
              onChange={(e) => setBulkCelebrity(e.target.value)}
            />
          </div>

          <div
            className={`vault-dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => { if (!isAdmin) return; e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={async (e) => {
              if (!isAdmin) return;
              e.preventDefault();
              setDragging(false);
              const items = await collectDroppedFiles(e.dataTransfer);
              if (items.length) uploadEntries(items);
            }}
          >
            <p className="vault-helper-text">
              {isAdmin
                ? "Drag & drop your entire main celebrity folder here (uploaded automatically in fast batches)"
                : "Employee accounts can view and use shared Celebrity Vault clips below. Uploads are managed by Owner/Admin."}
            </p>
            <div className="vault-upload-actions">
              <label className={`button button-secondary ${!isAdmin ? "disabled" : ""}`} style={{ cursor: isAdmin ? "pointer" : "not-allowed", margin: 0, opacity: isAdmin ? 1 : 0.6 }}>
                <ImageIcon size={15} />
                <span>Upload Files</span>
                <input
                  type="file"
                  multiple
                  accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.mkv,.m4v"
                  style={{ display: "none" }}
                  disabled={busy || !isAdmin}
                  onChange={(e) => uploadBulkFiles(e.target.files)}
                />
              </label>
              <label className={`button button-primary ${!isAdmin ? "disabled" : ""}`} style={{ cursor: isAdmin ? "pointer" : "not-allowed", margin: 0, opacity: isAdmin ? 1 : 0.6 }}>
                <FolderUp size={15} />
                <span>Upload Main Folder</span>
                <input
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  style={{ display: "none" }}
                  disabled={busy || !isAdmin}
                  onChange={(e) => uploadBulkFiles(e.target.files)}
                />
              </label>
            </div>
          </div>

          <p className="vault-helper-text">
            Automatically detects celebrity subfolders inside your main folder (e.g. <code>MainFolder/Stephen A Smith/angry.mp4</code>).
          </p>
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
          {["OWNER", "ADMIN"].includes(localStorage.getItem("role")) && (
            <Button variant="secondary" disabled={busy} onClick={() => connectFolder(null)}>
              <RefreshCw size={14} />
              <span>Rescan</span>
            </Button>
          )}
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
