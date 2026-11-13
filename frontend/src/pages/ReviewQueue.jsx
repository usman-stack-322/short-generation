import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  Download,
  Film,
  Lock,
  Send,
  Sparkles,
  Trash2,
  User,
  XCircle,
} from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

const TABS = [
  ["pending_review", "Pending Approval"],
  ["approved", "Approved"],
  ["rejected", "Changes Requested"],
  ["draft", "Unsubmitted Drafts"],
  ["all", "All Shorts"],
];

function badgeText(reviewStatus) {
  switch (reviewStatus) {
    case "pending_review":
      return "Pending Approval";
    case "approved":
      return "Approved";
    case "rejected":
      return "Changes Requested";
    case "uploaded":
      return "Approved / Exported";
    default:
      return "Draft";
  }
}

export default function ReviewQueue() {
  const role = localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);
  const [drafts, setDrafts] = useState(null);
  const [filter, setFilter] = useState("pending_review");
  const [selectedId, setSelectedId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  async function loadQueue() {
    try {
      const rows = await api("/title-shorts");
      const allDrafts = rows || [];
      setDrafts(allDrafts);
      if (allDrafts.length > 0 && !allDrafts.some((r) => r.id === selectedId)) {
        const firstPending = allDrafts.find((r) => r.review_status === "pending_review") || allDrafts[0];
        setSelectedId(firstPending.id);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadQueue();
  }, [isAdmin]);

  async function submitForReview(id) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api(`/projects/${id}/submit-review`, { method: "POST" });
      setStatus("Submitted for workspace owner approval.");
      await loadQueue();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const visibleDrafts = (drafts || []).filter((r) => {
    if (filter === "all") return true;
    return (r.review_status || "draft") === filter;
  });

  const selected =
    visibleDrafts.find((r) => r.id === selectedId) ||
    (drafts || []).find((r) => r.id === selectedId) ||
    visibleDrafts[0] ||
    null;

  useEffect(() => {
    if (!selected) return;
    setNote(selected.review_note || "");
  }, [selected?.id]);

  async function submitDecision(action) {
    if (!selected) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const updated = await api(`/projects/${selected.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, note }),
      });
      setStatus(
        action === "approve"
          ? `Approved "${updated.title}". Employee download is now unlocked.`
          : `Sent revision feedback for "${updated.title}".`
      );
      await loadQueue();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteDraft(item) {
    if (!window.confirm(`Permanently delete "${item.title}"? This removes the rendered video as well.`)) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api(`/projects/${item.id}`, { method: "DELETE" });
      setStatus(`Deleted "${item.title}".`);
      if (selectedId === item.id) setSelectedId("");
      await loadQueue();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !drafts) return <Notice>{error}</Notice>;
  if (!drafts) return <Loading />;

  return (
    <div>
      <PageHeader
        eyebrow="OWNER APPROVAL & EXPORTS"
        title="Review Queue"
        description="Inspect drafts and rendered shorts from you and your employees, approve for MP4 download, or remove unwanted drafts."
      />

      {error && <Notice>{error}</Notice>}
      {status && <Notice type="success">{status}</Notice>}

      <div className="vault-pill-group" style={{ marginBottom: 18 }}>
        {TABS.map(([key, label]) => {
          const count =
            key === "all"
              ? drafts.length
              : drafts.filter((d) => (d.review_status || "draft") === key).length;
          return (
            <button
              key={key}
              type="button"
              className={`filter-pill ${filter === key ? "active" : ""}`}
              onClick={() => setFilter(key)}
            >
              {label} ({count})
            </button>
          );
        })}
      </div>

      {visibleDrafts.length === 0 ? (
        <section className="studio-card">
          <div className="empty-state">
            <div className="empty-icon">
              <Sparkles size={20} />
            </div>
            <strong>No items in this review tab</strong>
            <p>
              Rendered Title-to-Short drafts submitted by you or your employees appear here for owner review.
            </p>
            <Link to="/title-to-short">
              <Button>Create a Short</Button>
            </Link>
          </div>
        </section>
      ) : (
        <div className="studio-grid-2">
          <section className="studio-card">
            <div className="studio-card-head">
              <h2>
                <Film size={17} />
                <span>Submissions ({visibleDrafts.length})</span>
              </h2>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              {visibleDrafts.map((item) => {
                const isSelected = selected?.id === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    style={{
                      textAlign: "left",
                      padding: 14,
                      borderRadius: 12,
                      border: isSelected ? "2px solid var(--purple)" : "1px solid var(--line)",
                      background: isSelected ? "var(--bg-f9f7ff)" : "var(--surface-alt)",
                      display: "grid",
                      gap: 7,
                    }}
                  >
                    <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                      <span className={`studio-badge ${item.review_status || "draft"}`}>
                        {badgeText(item.review_status)}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {item.language} · {item.output_duration ? `${Math.round(item.output_duration)}s` : `${item.duration}s`}
                      </span>
                    </div>
                    <strong style={{ fontSize: 14, color: "var(--text)" }}>{item.title}</strong>
                    <div className="studio-action-row">
                      {item.creator_name && (
                        <span className="mood-tag">
                          <User size={11} style={{ marginRight: 4, verticalAlign: "middle" }} />
                          {item.creator_name}
                        </span>
                      )}
                      <span className="mood-tag">{item.style}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          {selected && (
            <section className="studio-card">
              <div className="studio-card-head">
                <div>
                  <span className={`studio-badge ${selected.review_status || "draft"}`}>
                    {badgeText(selected.review_status)}
                  </span>
                  <h2 style={{ marginTop: 8 }}>{selected.title}</h2>
                  <p className="studio-subtext">
                    Created by {selected.creator_name || "Workspace Member"} ·{" "}
                    {selected.voice?.provider || "TTS"} ({selected.voice?.voice || "Auto"})
                  </p>
                </div>
                {(isAdmin || ["draft", "rejected"].includes(selected.review_status || "draft")) ? (
                  <Button
                    variant="danger"
                    loading={busy}
                    onClick={() => deleteDraft(selected)}
                    title={isAdmin ? "Delete short permanently" : "Remove unsubmitted draft"}
                  >
                    <Trash2 size={14} />
                    <span>{isAdmin ? "Delete" : "Remove Draft"}</span>
                  </Button>
                ) : (
                  <span className="studio-lock-pill">
                    <Lock size={12} />
                    <span>Delete Owner Only</span>
                  </span>
                )}
              </div>

              {selected.video_url && (
                <div
                  style={{
                    borderRadius: 12,
                    overflow: "hidden",
                    background: "#0f172a",
                    marginBottom: 16,
                    display: "grid",
                    placeItems: "center",
                  }}
                >
                  <video
                    key={selected.video_url}
                    controls
                    preload="metadata"
                    src={mediaUrl(selected.video_url)}
                    style={{ width: "100%", maxHeight: 420, objectFit: "contain" }}
                  />
                </div>
              )}

              <div className="studio-field">
                <label className="studio-label" htmlFor="review-note">Owner Feedback / Approval Note</label>
                <textarea
                  id="review-note"
                  rows={2}
                  readOnly={!isAdmin}
                  placeholder={isAdmin ? "Optional feedback for employee or approval note..." : "Owner feedback will appear here once reviewed..."}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>

              <div className="studio-action-row" style={{ marginBottom: 18 }}>
                {selected.video_url && (isAdmin || ["approved", "uploaded"].includes(selected.review_status)) ? (
                  <a
                    href={mediaUrl(`${selected.video_url}&download=true`)}
                    download={`short-${selected.id}.mp4`}
                  >
                    <Button>
                      <Download size={15} />
                      <span>Download Final MP4</span>
                    </Button>
                  </a>
                ) : selected.video_url ? (
                  <span className="studio-lock-pill">
                    <Lock size={12} />
                    <span>Download locked until approved</span>
                  </span>
                ) : null}

                {isAdmin ? (
                  <>
                    <Button
                      variant="secondary"
                      loading={busy}
                      onClick={() => submitDecision("approve")}
                    >
                      <CheckCircle2 size={15} />
                      <span>Approve &amp; Unlock for Creator</span>
                    </Button>
                    <Button
                      variant="secondary"
                      loading={busy}
                      onClick={() => submitDecision("request_changes")}
                    >
                      <XCircle size={15} />
                      <span>Request Changes</span>
                    </Button>
                  </>
                ) : (
                  <>
                    {selected.video_url && selected.review_status !== "pending_review" && selected.review_status !== "approved" && (
                      <Button
                        loading={busy}
                        onClick={() => submitForReview(selected.id)}
                      >
                        <Send size={15} />
                        <span>Submit for Owner Approval</span>
                      </Button>
                    )}
                    <Button variant="secondary" disabled>
                      <Lock size={14} />
                      <span>Approve (Owner Only)</span>
                    </Button>
                  </>
                )}
                <Button
                  variant="secondary"
                  type="button"
                  onClick={() => {
                    const text = `${selected.title}\n\n${selected.script || ""}\n\n#Shorts`;
                    navigator.clipboard?.writeText(text).then(() => setStatus("Copied Title & Description for manual upload.")).catch(() => {});
                  }}
                >
                  <span>Copy Title &amp; Description</span>
                </Button>
                <Link to={`/title-to-short/${selected.id}`}>
                  <Button variant="secondary">Open Script &amp; Scenes</Button>
                </Link>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
