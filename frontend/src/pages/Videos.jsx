import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  Download,
  Film,
  Lock,
  Plus,
  Search,
  Send,
  Trash2,
  XCircle,
} from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

const FILTER_TABS = [
  ["all", "All Shorts"],
  ["pending_review", "Pending Approval"],
  ["approved", "Approved & Ready"],
  ["rejected", "Changes Requested"],
  ["rendering", "Drafts / Rendering"],
];

function statusLabel(reviewStatus) {
  switch (reviewStatus) {
    case "pending_review":
      return "Pending Approval";
    case "approved":
      return "Approved";
    case "rejected":
      return "Changes Requested";
    case "uploaded":
      return "Uploaded";
    case "rendering":
      return "Rendering";
    default:
      return "Draft";
  }
}

export default function Videos() {
  const role = localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);
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

  async function submitForReview(id) {
    setBusyId(id);
    setError("");
    setBanner("");
    try {
      await api(`/projects/${id}/submit-review`, { method: "POST" });
      setBanner("Submitted to workspace owner for approval. Download unlocks once approved.");
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId("");
    }
  }

  async function reviewShort(id, action) {
    const note =
      action === "reject"
        ? window.prompt("Optional note explaining requested changes:", "Please revise voiceover or scenes")
        : "Approved";
    if (action === "reject" && note === null) return;
    setBusyId(id);
    setError("");
    setBanner("");
    try {
      await api(`/projects/${id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, note: note || "" }),
      });
      setBanner(
        action === "approve"
          ? "Short approved! Download is now unlocked for the creator."
          : "Changes requested on short."
      );
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId("");
    }
  }

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
    const st = item.review_status || "draft";
    if (filter === "rendering") {
      if (!["rendering", "draft"].includes(st)) return false;
    } else if (filter !== "all" && st !== filter) {
      return false;
    }
    if (!q) return true;
    return (
      item.title.toLowerCase().includes(q) ||
      (item.creator_name || "").toLowerCase().includes(q) ||
      item.language.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        eyebrow={isAdmin ? "WORKSPACE SHORTS LIBRARY" : "MY SHORTS & DOWNLOADS"}
        title={isAdmin ? "All Workspace Videos" : "My Videos & Downloads"}
        description={
          isAdmin
            ? "Review, download, approve, or clean up shorts created across your workspace."
            : "Your created shorts only. Downloads unlock automatically once your workspace owner approves them."
        }
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
            placeholder={isAdmin ? "Search title, language, or creator..." : "Search your shorts..."}
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
                ? "Create your first AI Short from any title to preview, submit for approval, and download."
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
            const st = item.review_status || "draft";
            const canDownload = isAdmin || ["approved", "uploaded"].includes(st);
            const downloadHref = item.video_url
              ? mediaUrl(`${item.video_url}&download=true`)
              : null;

            return (
              <article key={item.id} className="studio-video-card">
                <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                  <span className={`studio-badge ${st}`}>{statusLabel(st)}</span>
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
                    {isAdmin && item.creator_name && (
                      <span className="mood-tag">Creator: {item.creator_name}</span>
                    )}
                    <span className="mood-tag">{item.style}</span>
                  </div>
                  {item.review_note && (
                    <p className="studio-subtext" style={{ marginTop: 8 }}>
                      Note: {item.review_note}
                    </p>
                  )}
                </div>

                <div className="studio-action-row" style={{ marginTop: "auto" }}>
                  <Link to={`/title-to-short/${item.id}`}>
                    <Button variant="secondary">Open Editor</Button>
                  </Link>

                  {!isAdmin && item.status === "ready" && ["draft", "rejected"].includes(st) && (
                    <Button
                      loading={busyId === item.id}
                      onClick={() => submitForReview(item.id)}
                    >
                      <Send size={13} />
                      <span>Submit for Approval</span>
                    </Button>
                  )}

                  {isAdmin && item.status === "ready" && st === "pending_review" && (
                    <>
                      <Button
                        loading={busyId === item.id}
                        onClick={() => reviewShort(item.id, "approve")}
                      >
                        <CheckCircle2 size={13} />
                        <span>Approve</span>
                      </Button>
                      <Button
                        variant="secondary"
                        loading={busyId === item.id}
                        onClick={() => reviewShort(item.id, "reject")}
                      >
                        <XCircle size={13} />
                        <span>Reject</span>
                      </Button>
                    </>
                  )}

                  {item.video_url && canDownload && (
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

                  {item.video_url && !canDownload && (
                    <span className="studio-lock-pill">
                      <Lock size={12} />
                      <span>Locked until approved</span>
                    </span>
                  )}

                  {(isAdmin || ["draft", "rejected"].includes(st)) && (
                    <Button
                      variant="danger"
                      loading={busyId === item.id}
                      onClick={() => deleteShort(item)}
                      title={isAdmin ? "Delete short permanently" : "Remove unsubmitted draft"}
                    >
                      <Trash2 size={13} />
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
