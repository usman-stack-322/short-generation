import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Download,
  Film,
  FolderOpen,
  Lock,
  Plus,
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

  const role = data.role || localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);
  const summary = data.shorts_summary || {
    total: 0,
    rendering: 0,
    pending_review: 0,
    approved: 0,
    rejected: 0,
    uploaded: 0,
  };
  const recentShorts = data.recent_shorts || [];

  return (
    <div>
      {error && <Notice>{error}</Notice>}
      {banner && <Notice type="success">{banner}</Notice>}

      <section className="studio-hero">
        <div>
          <span className={`studio-role-chip ${isAdmin ? "admin" : "member"}`}>
            <ShieldCheck size={13} />
            <span>
              {role === "OWNER"
                ? "Workspace Owner"
                : role === "ADMIN"
                ? "Isolated Workspace Owner"
                : "Employee Creator"}
            </span>
          </span>
          <h1>Welcome back, {data.user}</h1>
          <p>
            {isAdmin
              ? "Manage your private workspace, review employee-created shorts, approve final videos, and download ready-to-publish MP4s."
              : "Create high-retention Shorts from any title, pick visuals from the shared Celebrity Vault, submit for approval, and download once approved."}
          </p>
        </div>
        <div className="studio-action-row">
          <Link to="/title-to-short">
            <Button>
              <Plus size={16} />
              <span>Create New Short</span>
            </Button>
          </Link>
          <Link to="/review-queue">
            <Button variant="secondary">
              <Sparkles size={15} />
              <span>Review Queue ({summary.pending_review + (data.waiting_approval || 0)})</span>
            </Button>
          </Link>
          <Link to="/videos">
            <Button variant="secondary">
              <Film size={15} />
              <span>My Videos &amp; Downloads</span>
            </Button>
          </Link>
        </div>
      </section>

      <div className="studio-kpi-grid">
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Pending Owner Review</span>
            <Clock3 size={16} />
          </div>
          <strong>{summary.pending_review + (data.waiting_approval || 0)}</strong>
          <small>{isAdmin ? "Rendered shorts awaiting your approval" : "Download unlocks after Owner approval"}</small>
        </div>
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Approved Shorts</span>
            <CheckCircle2 size={16} />
          </div>
          <strong>{summary.approved + summary.uploaded + (data.approved || 0)}</strong>
          <small>Ready to download as 9:16 MP4</small>
        </div>
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>Total Shorts</span>
            <Film size={16} />
          </div>
          <strong>{summary.total}</strong>
          <small>{isAdmin ? "Created across this workspace" : "Only visible to you & workspace owner"}</small>
        </div>
        <div className="studio-kpi-card">
          <div className="studio-kpi-top">
            <span>{isAdmin ? "Team & Processing" : "Processing Drafts"}</span>
            <Users size={16} />
          </div>
          <strong>{isAdmin ? `${data.total_members || 1} members` : `${summary.rendering} active`}</strong>
          <small>{isAdmin ? `${summary.rendering} active rendering / draft` : "Active script & render drafts"}</small>
        </div>
      </div>

      <div className="studio-grid-2">
        <section className="studio-card">
          <div className="studio-card-head">
            <div>
              <h2>
                <Film size={17} />
                <span>{isAdmin ? "Workspace Recent Shorts" : "My Recent Shorts"}</span>
              </h2>
              <p className="studio-subtext">
                {isAdmin
                  ? "Review and approve employee drafts before downloads unlock."
                  : "Track generation status and download your approved final shorts."}
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
                const canDownload = isAdmin || ["approved", "uploaded"].includes(item.review_status);
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
                        <span className={`studio-badge ${item.review_status || "draft"}`}>
                          {formatShortStatus(item.review_status)}
                        </span>
                        {isAdmin && item.creator_name && (
                          <span className="mood-tag">By {item.creator_name}</span>
                        )}
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {item.language} • {item.output_duration ? `${Math.round(item.output_duration)}s` : `${item.duration}s`}
                      </span>
                    </div>

                    <div>
                      <strong style={{ fontSize: 14, color: "var(--text)" }}>{item.title}</strong>
                      {item.review_note && (
                        <p className="studio-subtext">Review note: {item.review_note}</p>
                      )}
                    </div>

                    <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                      <Link to={`/title-to-short/${item.id}`}>
                        <Button variant="secondary">Open Project</Button>
                      </Link>
                      <div className="studio-action-row">
                        {isAdmin && item.review_status === "pending_review" && item.status === "ready" && (
                          <Button
                            loading={busyId === item.id}
                            onClick={() => quickApprove(item.id)}
                          >
                            <CheckCircle2 size={14} />
                            <span>Approve</span>
                          </Button>
                        )}
                        {item.video_url && canDownload && (
                          <a href={downloadHref} download={`short-${item.id}-rev${latestRev}.mp4`}>
                            <Button variant="secondary">
                              <Download size={14} />
                              <span>Download MP4</span>
                            </Button>
                          </a>
                        )}
                        {item.video_url && !canDownload && (
                          <span className="studio-lock-pill">
                            <Lock size={12} />
                            <span>Approval required to download</span>
                          </span>
                        )}
                        {(isAdmin || ["draft", "rejected"].includes(item.review_status || "draft")) && (
                          <Button
                            variant="danger"
                            loading={busyId === item.id}
                            onClick={() => quickDeleteShort(item)}
                            title={isAdmin ? "Delete short" : "Remove draft"}
                          >
                            <Trash2 size={14} />
                          </Button>
                        )}
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
                {isAdmin
                  ? "Generate, review, approve, and download final 9:16 MP4 videos directly — ready to upload manually to any channel you want."
                  : "Create Shorts from Title, use shared Celebrity Vault visuals, remove unsubmitted drafts anytime, and download approved MP4 files directly."}
              </p>
            </div>
          </section>

          <section className="studio-card">
            <div className="studio-card-head">
              <h2>
                <Users size={17} />
                <span>Team &amp; Studio Resources</span>
              </h2>
              <Link to="/team" className="text-link">
                Team &amp; Roles <ArrowRight size={13} />
              </Link>
            </div>
            <p className="studio-subtext" style={{ marginBottom: 12 }}>
              {isAdmin
                ? `Active workspace members: ${data.total_members || 1}. Generate shareable invite links for Employees or create a 100% isolated Friend workspace.`
                : "Use the shared workspace Celebrity Folder when building scenes, then submit for Owner review to unlock MP4 download."}
            </p>
            <div className="studio-action-row">
              <Link to="/team">
                <Button variant="secondary">
                  <Users size={14} />
                  <span>{isAdmin ? "Roles & Invite Links" : "View Team & Roles"}</span>
                </Button>
              </Link>
              <Link to="/celebrity-library">
                <Button variant="secondary">
                  <FolderOpen size={14} />
                  <span>Celebrity Folder</span>
                </Button>
              </Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
