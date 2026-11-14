import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Download,
  Film,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

const FILTER_TABS = [
  ["all", "All Videos"],
  ["ready", "Ready MP4"],
  ["rendering", "Drafts / Rendering"],
];

function statusLabel(item) {
  if (item.video_url || item.status === "ready") return "Ready MP4";
  if (item.status === "failed") return "Stopped / Failed";
  if (["validating", "visuals", "voiceover", "rendering"].includes(item.status)) return "Rendering";
  return "Draft";
}

export default function Videos() {
  const [shorts, setShorts] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");

  async function loadAll() {
    try {
      const shortRows = await api("/title-shorts");
      setShorts(shortRows);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadAll();
    const timer = setInterval(loadAll, 12000);
    return () => clearInterval(timer);
  }, []);

  async function deleteShort(item) {
    if (!window.confirm(`Delete "${item.title}" permanently?`)) return;
    setBusyId(item.id);
    setError("");
    setBanner("");
    try {
      await api(`/title-shorts/${item.id}`, { method: "DELETE" });
      setBanner(`Deleted "${item.title}".`);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId("");
    }
  }

  if (error && !shorts) return <Notice>{error}</Notice>;
  if (!shorts) return <Loading />;

  const q = query.trim().toLowerCase();
  const visibleShorts = shorts.filter((item) => {
    const isReady = Boolean(item.video_url) || item.status === "ready";
    if (filter === "ready" && !isReady) return false;
    if (filter === "rendering" && isReady) return false;
    if (!q) return true;
    return (
      item.title.toLowerCase().includes(q) ||
      item.language.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        eyebrow="VIDEOS & EXPORTS"
        title="My Videos & Downloads"
        description="Preview, download final 9:16 MP4 files directly, or clean up drafts inside your studio."
        action={
          <Link to="/title-to-short">
            <Button>
              <Plus size={16} />
              <span>Create Short</span>
            </Button>
          </Link>
        }
      />

      {error && <Notice>{error}</Notice>}
      {banner && <Notice type="success">{banner}</Notice>}

      <div className="vault-filter-bar" style={{ marginBottom: 18 }}>
        <div className="vault-search-wrap studio-input-icon-wrap">
          <span className="studio-input-icon">
            <Search size={15} />
          </span>
          <input
            aria-label="Search shorts"
            style={{ paddingLeft: 36 }}
            placeholder="Search by title or language..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="vault-pill-group">
          {FILTER_TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`filter-pill ${filter === key ? "active" : ""}`}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {visibleShorts.length === 0 ? (
        <section className="studio-card">
          <div className="empty-state">
            <div className="empty-icon">
              <Film size={20} />
            </div>
            <strong>No matching shorts found</strong>
            <p>
              {shorts.length === 0
                ? "Create your first AI Short from any title to preview and download as MP4."
                : "Try switching filter tabs or clearing your search box."}
            </p>
            <Link to="/title-to-short">
              <Button>
                <Plus size={15} />
                <span>Create Short</span>
              </Button>
            </Link>
          </div>
        </section>
      ) : (
        <div className="studio-video-grid">
          {visibleShorts.map((item) => {
            const canDownload = Boolean(item.video_url);
            const downloadHref = item.video_url
              ? mediaUrl(`${item.video_url}&download=true`)
              : null;

            return (
              <article key={item.id} className="studio-video-card">
                <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                  <span className={`studio-badge ${canDownload ? "approved" : "draft"}`}>{statusLabel(item)}</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {item.language} · {item.output_duration ? `${Math.round(item.output_duration)}s` : `${item.duration}s`}
                  </span>
                </div>

                {item.video_url && (
                  <div className="studio-video-preview">
                    <video
                      key={item.video_url}
                      controls
                      preload="metadata"
                      src={mediaUrl(item.video_url)}
                    />
                  </div>
                )}

                <div>
                  <h3 style={{ margin: "0 0 6px", fontSize: 15, lineHeight: 1.35 }}>
                    {item.title}
                  </h3>
                  <div className="studio-action-row">
                    <span className="mood-tag">{item.style}</span>
                  </div>
                </div>

                <div className="studio-action-row" style={{ marginTop: "auto" }}>
                  <Link to={`/title-to-short/${item.id}`}>
                    <Button variant="secondary">Open Editor</Button>
                  </Link>

                  {downloadHref && canDownload && (
                    <>
                      <a href={downloadHref} download={`short-${item.id}.mp4`}>
                        <Button>
                          <Download size={13} />
                          <span>Download MP4</span>
                        </Button>
                      </a>
                      <Button
                        variant="secondary"
                        type="button"
                        onClick={() => {
                          const text = `${item.title}\n\n${item.script || ""}\n\n#Shorts`;
                          navigator.clipboard?.writeText(text).then(() => setBanner(`Copied title & script for "${item.title}".`)).catch(() => {});
                        }}
                      >
                        <span>Copy Title pack</span>
                      </Button>
                    </>
                  )}

                  <Button
                    variant="danger"
                    loading={busyId === item.id}
                    onClick={() => deleteShort(item)}
                    title="Delete video or draft"
                  >
                    <Trash2 size={13} />
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
