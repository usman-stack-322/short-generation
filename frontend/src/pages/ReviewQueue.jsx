import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../services/api";
import { PageHeader, EmptyState } from "../components/Shell";
import { Button } from "../components/UI";
import { CheckCircle2, Film, RotateCcw, Youtube } from "lucide-react";

export default function ReviewQueue() {
  const [drafts, setDrafts] = useState([]);
  const [channels, setChannels] = useState([]);
  const [selected, setSelected] = useState(null);
  const [note, setNote] = useState("");
  const [privacy, setPrivacy] = useState("private");
  const [channelId, setChannelId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const role = localStorage.getItem("role") || "MEMBER";
  const canApprove = ["OWNER", "ADMIN"].includes(role);

  async function load() {
    try {
      const [rows, ch] = await Promise.all([api("/title-shorts"), api("/channels")]);
      setDrafts(rows);
      setChannels(ch);
      const reviewList = rows.filter((d) => d.video_url || ["pending_review", "approved", "rejected", "uploaded"].includes(d.review_status));
      if (selected) {
        const updated = rows.find((r) => r.id === selected.id);
        if (updated) setSelected(updated);
      } else if (reviewList.length > 0) {
        setSelected(reviewList[0]);
        setNote(reviewList[0].review_note || "");
        setChannelId(reviewList[0].channel_id || "");
      }
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function submitReview(action) {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const updated = await api(`/projects/${selected.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, note }),
      });
      setSelected(updated);
      setMessage(`Project marked as ${updated.review_status}.`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function approveAndUpload() {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      if (selected.review_status !== "approved") {
        await api(`/projects/${selected.id}/review`, {
          method: "POST",
          body: JSON.stringify({ action: "approve", note }),
        });
      }
      const res = await api(`/projects/${selected.id}/upload-youtube`, {
        method: "POST",
        body: JSON.stringify({
          channel_id: channelId || selected.channel_id || null,
          title: (selected.scope?.proposed_title || selected.title).slice(0, 100),
          description: selected.analysis?.angle || selected.title,
          privacy_status: privacy,
        }),
      });
      setSelected(res.draft);
      setMessage(
        res.mode === "youtube_api"
          ? `Uploaded to YouTube: ${res.youtube_url}`
          : `Mock/Fallback YouTube Upload recorded (${res.youtube_url}). Add client_secrets.json + OAuth for live YouTube upload.`
      );
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const reviewable = drafts.filter((d) => d.video_url || ["pending_review", "approved", "rejected", "uploaded"].includes(d.review_status));

  return (
    <div>
      <PageHeader
        eyebrow="APPROVAL WORKFLOW"
        title="Review Queue & YouTube Upload"
        description="Preview rendered 9:16 shorts, request scene edits, approve, and publish to your workspace YouTube channel."
      />

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {message && <div className="notice notice-success" role="status">{message}</div>}

      {reviewable.length === 0 ? (
        <EmptyState
          title="No rendered shorts in the review queue"
          detail="Render a short in Create Short to submit it for review."
          action={<Link className="button button-primary" to="/title-to-short">Create Short</Link>}
        />
      ) : (
        <div className="review-studio-grid">
          <div>
            <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#475569" }}>
              Shorts Projects ({reviewable.length})
            </h3>
            {reviewable.map((d) => (
              <button
                key={d.id}
                type="button"
                className={`review-project-item ${selected?.id === d.id ? "selected" : ""}`}
                onClick={() => { setSelected(d); setNote(d.review_note || ""); setChannelId(d.channel_id || ""); }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span className={`status-badge ${d.review_status || "draft"}`}>
                    {(d.review_status || "draft").replaceAll("_", " ")}
                  </span>
                  <span style={{ fontSize: 11.5, color: "#64748b" }}>{d.duration}s · {d.language}</span>
                </div>
                <strong style={{ display: "block", fontSize: 13.5, color: "#0f172a", lineHeight: 1.4 }}>
                  {d.scope?.proposed_title || d.title}
                </strong>
                {d.youtube_url && (
                  <div style={{ fontSize: 12, color: "#4f46e5", marginTop: 6 }}>YouTube: {d.youtube_url}</div>
                )}
              </button>
            ))}
          </div>

          {selected && (
            <div className="studio-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>{selected.scope?.proposed_title || selected.title}</h3>
                <span className={`status-badge ${selected.review_status || "draft"}`}>
                  {(selected.review_status || "draft").replaceAll("_", " ")}
                </span>
              </div>

              {selected.video_url && (
                <div className="phone-frame">
                  <video key={selected.video_url} src={mediaUrl(selected.video_url)} controls playsInline />
                </div>
              )}

              <div className="studio-field">
                <label className="studio-label" htmlFor="review-note">Reviewer Notes &amp; Feedback</label>
                <textarea
                  id="review-note"
                  rows={2}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Optional feedback for scene edits..."
                />
              </div>

              {canApprove ? (
                <>
                  <div className="studio-controls-grid">
                    <div className="studio-field">
                      <label className="studio-label" htmlFor="review-channel">Destination YouTube Channel</label>
                      <select id="review-channel" value={channelId} onChange={(e) => setChannelId(e.target.value)}>
                        <option value="">Workspace Default</option>
                        {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>
                    <div className="studio-field">
                      <label className="studio-label" htmlFor="review-privacy">YouTube Privacy Status</label>
                      <select id="review-privacy" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
                        <option value="private">Private</option>
                        <option value="unlisted">Unlisted</option>
                        <option value="public">Public</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
                    <Button disabled={busy} loading={busy} onClick={approveAndUpload}>
                      <Youtube size={16} /><span>Approve &amp; Upload to YouTube</span>
                    </Button>
                    <Button variant="secondary" disabled={busy} onClick={() => submitReview("approve")}>
                      <CheckCircle2 size={15} /><span>Approve Only</span>
                    </Button>
                    <Button variant="secondary" disabled={busy} onClick={() => submitReview("request_changes")}>
                      <RotateCcw size={15} /><span>Request Changes</span>
                    </Button>
                    <Link className="button button-secondary" to={`/title-to-short/${selected.id}`}>
                      <Film size={15} /><span>Re-render / Edit Scenes</span>
                    </Link>
                  </div>
                </>
              ) : (
                <div style={{ display: "flex", gap: 10, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                  <p className="vault-helper-text">Submitted for Owner/Admin review. Members cannot upload directly to YouTube.</p>
                  <Link className="button button-secondary" to={`/title-to-short/${selected.id}`}>Re-render / Edit Scenes</Link>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
