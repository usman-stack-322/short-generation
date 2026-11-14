import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Download,
  Film,
  FolderOpen,
  Lock,
  Plus,
  Share2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { Button, Loading, Notice } from "../components/UI";

function formatShortStatus(reviewStatus) {
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
      return "Drafting";
  }
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [banner, setBanner] = useState("");

  async function loadDashboard() {
    try {
      const payload = await api("/dashboard");
      setData(payload);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(() => {
      loadDashboard();
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  async function quickApprove(shortId) {
    setBusyId(shortId);
    setError("");
    setBanner("");
    try {
      await api(`/projects/${shortId}/review`, {
        method: "POST",
        body: JSON.stringify({ action: "approve", note: "Approved from dashboard" }),
      });
      setBanner("Short approved! The creator can now download the final MP4.");
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId("");
    }
  }

  async function quickDeleteShort(item) {
    if (!window.confirm(`Remove draft "${item.title}" permanently?`)) return;
    setBusyId(item.id);
    setError("");
    setBanner("");
    try {
      await api(`/title-shorts/${item.id}`, { method: "DELETE" });
      setBanner(`Removed "${item.title}".`);
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId("");
    }
  }

  if (error && !data) {
    return <Notice>{error}</Notice>;
  }
  if (!data) {
    return <Loading />;
  }

  const summary = data.shorts_summary || {
    total: 0,
    rendering: 0,
    pending_review: 0,
    approved: 0,
    rejected: 0,
    uploaded: 0,
  };
  const recentShorts = data.recent_shorts || [];
  const readyCount = recentShorts.filter((s) => Boolean(s.video_url) || s.status === "ready").length;

  return (
    <div>
      {error && <Notice>{error}</Notice>}
      {banner && <Notice type="success">{banner}</Notice>}

      <section className="studio-hero">
        <div>
          <span className="studio-role-chip admin">
            <Sparkles size={13} />
            <span>Creator Studio</span>
          </span>
          <h1>Welcome back, {data.user}</h1>
          <p>
            Create high-retention 9:16 AI Shorts from any title, sync your Celebrity Folder once, and download ready-to-publish MP4 videos directly.
          </p>
        </div>
        <div className="studio-action-row">
          <Link to="/title-to-short">
            <Button>
              <Plus size={16} />
              <span>Create New Short</span>
            </Button>
          </Link>
          <Link to="/celebrity-library">
            <Button variant="secondary">
              <FolderOpen size={15} />
              <span>Celebrity Folder</span>
            </Button>
          </Link>
          <Link to="/videos">
            <Button variant="secondary">
              <Film size={15} />
              <span>My Videos &amp; Downloads</span>
            </Button>
          </Link>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              const url = `${window.location.origin}/register`;
              navigator.clipboard?.writeText(url).then(() => {
                setBanner(`Signup link copied (${url}) — anyone signing up with email & password gets their own private workspace.`);
              }).catch(() => {
                setBanner(`Share this signup link: ${url}`);
              });
            }}
          >
            <Share2 size={15} />
            <span>Share Signup Link</span>
          </Button>
        </div>
      </section>

      <div className="studio-kpi-grid">
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Ready to Download</span>
            <CheckCircle2 size={16} />
          </div>
          <strong>{summary.approved + summary.uploaded + summary.pending_review || readyCount}</strong>
          <small>Final 9:16 MP4 videos ready</small>
        </div>
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Drafts &amp; Rendering</span>
            <Clock3 size={16} />
          </div>
          <strong>{summary.rendering}</strong>
          <small>Active scripts and renders</small>
        </div>
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Total Shorts</span>
            <Film size={16} />
          </div>
          <strong>{summary.total}</strong>
          <small>Saved inside your studio</small>
        </div>
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Export Format</span>
            <Download size={16} />
          </div>
          <strong>MP4 9:16</strong>
          <small>Direct manual download enabled</small>
        </div>
      </div>

      <div className="studio-grid-2">
        <section className="studio-card">
          <div className="studio-card-head">
            <div>
              <h2>
                <Film size={17} />
                <span>Recent Shorts</span>
              </h2>
              <p className="studio-subtext">
                Open drafts, preview renders, or download ready MP4 files directly.
              </p>
            </div>
            <Link to="/videos" className="text-link">
              View all <ArrowRight size={13} />
            </Link>
          </div>

          {recentShorts.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Sparkles size={20} />
              </div>
              <strong>No shorts created yet</strong>
              <p>
                Start with a title and topic. The studio researches verified stories, selects curated or Celebrity Vault visuals, and renders 9:16 shorts with synced subtitles.
              </p>
              <Link to="/title-to-short">
                <Button>
                  <Plus size={15} />
                  <span>Create First Short</span>
                </Button>
              </Link>
            </div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              {recentShorts.map((item) => {
                const canDownload = Boolean(item.video_url);
                const latestRev = item.render_history?.at(-1)?.revision || item.revision;
                const downloadHref = item.video_url
                  ? mediaUrl(`${item.video_url}&download=true`)
                  : null;
                return (
                  <article
                    key={item.id}
                    style={{
                      border: "1px solid var(--line)",
                      borderRadius: 12,
                      padding: 14,
                      background: "var(--surface-alt)",
                      display: "grid",
                      gap: 10,
                    }}
                  >
                    <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                      <div className="studio-action-row">
                        <span className={`studio-badge ${canDownload ? "approved" : "draft"}`}>
                          {canDownload ? "Ready MP4" : "Draft"}
                        </span>
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {item.language} • {item.output_duration ? `${Math.round(item.output_duration)}s` : `${item.duration}s`}
                      </span>
                    </div>

                    <div>
                      <strong style={{ fontSize: 14, color: "var(--text)" }}>{item.title}</strong>
                    </div>

                    <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                      <Link to={`/title-to-short/${item.id}`}>
                        <Button variant="secondary">Open Project</Button>
                      </Link>
                      <div className="studio-action-row">
                        {downloadHref && canDownload && (
                          <a href={downloadHref} download={`short-${item.id}-rev${latestRev}.mp4`}>
                            <Button variant="secondary">
                              <Download size={14} />
                              <span>Download MP4</span>
                            </Button>
                          </a>
                        )}
                        <Button
                          variant="danger"
                          loading={busyId === item.id}
                          onClick={() => quickDeleteShort(item)}
                          title="Delete short or draft"
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <div style={{ display: "grid", gap: 16 }}>
          <section className="studio-card">
            <div className="studio-card-head">
              <h2>
                <Download size={17} />
                <span>Direct MP4 Export</span>
              </h2>
              <Link to="/videos" className="text-link">
                All Videos <ArrowRight size={13} />
              </Link>
            </div>
            <div className="studio-role-card">
              <strong>Download &amp; Publish Anywhere</strong>
              <p>
                Generate and download final 9:16 MP4 videos directly — ready to upload manually to YouTube, TikTok, or Instagram whenever you want.
              </p>
            </div>
          </section>

          <section className="studio-card">
            <div className="studio-card-head">
              <h2>
                <FolderOpen size={17} />
                <span>Celebrity Folder &amp; Media</span>
              </h2>
              <Link to="/celebrity-library" className="text-link">
                Open Folder <ArrowRight size={13} />
              </Link>
            </div>
            <p className="studio-subtext" style={{ marginBottom: 12 }}>
              Select your main Celebrity Folder once for ultra-fast delta sync. Already uploaded clips skip automatically, and background uploads stay active across pages.
            </p>
            <div className="studio-action-row">
              <Link to="/celebrity-library">
                <Button variant="secondary">
                  <FolderOpen size={14} />
                  <span>Celebrity Folder</span>
                </Button>
              </Link>
              <Link to="/library">
                <Button variant="secondary">
                  <Film size={14} />
                  <span>Media Library</span>
                </Button>
              </Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
