import LanguageSelect from "../components/LanguageSelect";
import VoiceStyleSelect from "../components/VoiceStyleSelect";
import { useEffect, useState } from "react";
import { Check, Download, Link2, Lock, Plus, Radio, Youtube } from "lucide-react";
import { api } from "../services/api";
import { PageHeader, EmptyState } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";
import { Modal } from "../components/UI";

export default function Channels() {
  const role = localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [channels, setChannels] = useState(isAdmin ? null : []);
  const [members, setMembers] = useState([]);
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    profile_image_url: "",
    youtube_channel_id: "",
    member_id: "",
    default_language: "en-US",
    default_voice: "en-US",
    daily_video_target: 1,
    approval_required: true,
  });

  async function load() {
    if (!isAdmin) {
      setChannels([]);
      return;
    }
    try {
      const [ch, mem] = await Promise.all([
        api("/channels"),
        api("/members").catch(() => []),
      ]);
      setChannels(ch || []);
      setMembers(mem || []);
    } catch (err) {
      setError(err.message);
      setChannels([]);
    }
  }

  useEffect(() => {
    load();
  }, [isAdmin]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/channels", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          member_id: form.member_id || null,
          daily_video_target: Number(form.daily_video_target),
        }),
      });
      setShow(false);
      setForm({ ...form, name: "", youtube_channel_id: "" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const result = await api("/youtube/connect");
      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  async function connectionAction(channel, action) {
    setBusy(true);
    setError("");
    try {
      await api(`/youtube/${action}`, {
        method: "POST",
        body: JSON.stringify({ channel_id: channel.id }),
      });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function configure(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/channels/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          member_id: editing.member_id,
          assigned_member_ids: editing.assigned_member_ids || [],
          default_language: editing.default_language,
          voice_style: editing.voice_style || "auto",
          approval_policy: editing.approval_policy,
          daily_video_target: Number(editing.daily_video_target),
          default_voice: editing.default_voice,
          tts_provider: editing.tts_provider,
          brand_color: editing.brand_color || "#61e8b6",
          automatic_evergreen_fallback: !!editing.automatic_evergreen_fallback,
          automatic_generation_enabled: !!editing.automatic_generation_enabled,
          generation_duration: Number(editing.generation_duration || 45),
          niche: editing.niche || "",
          evergreen_source_urls: editing.evergreen_source_urls || [],
        }),
      });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (channels === null) return <Loading />;

  return (
    <div>
      <PageHeader
        eyebrow="OPTIONAL YOUTUBE CONNECTION"
        title="My Channels"
        description="Channel connection is completely optional — download approved Shorts directly as MP4s without linking any YouTube channel."
        action={
          <div className="studio-action-row">
            <Button loading={busy} disabled={!isAdmin} onClick={connect}>
              {!isAdmin && <Lock size={14} />}
              <Youtube size={15} />
              <span>{isAdmin ? "Connect YouTube (Optional)" : "Connect Locked (Owner/Admin)"}</span>
            </Button>
            <Button variant="secondary" disabled={!isAdmin} onClick={() => setShow(true)}>
              {!isAdmin && <Lock size={14} />}
              <Plus size={15} />
              <span>{isAdmin ? "Create Local Channel" : "Add Channel Locked"}</span>
            </Button>
          </div>
        }
      />

      {error && <Notice>{error}</Notice>}

      <section className="studio-card" style={{ marginBottom: 18 }}>
        <div className="studio-card-head">
          <h2>
            <Download size={17} />
            <span>Manual Upload Workflow Enabled</span>
          </h2>
          {!isAdmin && (
            <span className="studio-lock-pill">
              <Lock size={12} />
              <span>Channel Edits Locked for Employees</span>
            </span>
          )}
        </div>
        <p className="studio-subtext">
          {isAdmin
            ? "You do not need to connect a YouTube channel to generate or download Shorts. Keep channels disconnected if you prefer downloading MP4 files and uploading to YouTube Studio yourself."
            : "Adding, removing, or connecting YouTube channels is restricted to Workspace Owners/Admins. You can create Shorts from Title and download approved MP4 files directly."}
        </p>
      </section>

      {!isAdmin ? (
        <section className="studio-card">
          <EmptyState
            title="Channels are Managed by Workspace Owner"
            detail="Employee accounts cannot add, remove, or connect YouTube channels. Once your Owner approves a Short you created, you can download the MP4 directly from My Videos."
            action={
              <span className="studio-lock-pill">
                <Lock size={13} />
                <span>Restricted Action</span>
              </span>
            }
          />
        </section>
      ) : channels.length > 0 ? (
        <div className="studio-video-grid">
          {channels.map((channel, index) => (
            <article className="studio-card" key={channel.id} style={{ display: "grid", gap: 12 }}>
              <div className="studio-action-row" style={{ justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div className={`channel-big-avatar channel-color-${index % 4}`}>
                    {channel.profile_image_url ? (
                      <img
                        src={channel.profile_image_url}
                        alt={channel.name}
                        style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 12 }}
                      />
                    ) : (
                      <Youtube size={22} />
                    )}
                  </div>
                  <div>
                    <h2 style={{ margin: 0, fontSize: 16 }}>{channel.name}</h2>
                    <p className="studio-subtext">{channel.youtube_channel_id || "Local manual channel"}</p>
                  </div>
                </div>
                <span className={`studio-badge ${channel.status === "connected" ? "connected" : "inactive"}`}>
                  {channel.status.replaceAll("_", " ")}
                </span>
              </div>

              <div className="channel-card-meta">
                <span><strong>Language</strong>{channel.default_language}</span>
                <span><strong>Daily target</strong>{channel.daily_video_target} videos</span>
                <span><strong>Owner / Lead</strong>{channel.member_name || "Workspace owner"}</span>
              </div>

              <div className="channel-card-bottom">
                <span><Check size={14} /> Approval required</span>
                <span><Link2 size={14} /> {channel.approval_policy.replaceAll("_", " ")}</span>
              </div>

              {channel.connection_error && <Notice>{channel.connection_error}</Notice>}

              <div className="studio-action-row">
                <Button variant="secondary" loading={busy} onClick={() => connectionAction(channel, "health")}>
                  Check health
                </Button>
                <Button variant="secondary" disabled={busy} onClick={connect}>
                  Reconnect
                </Button>
                {channel.status !== "demo" && (
                  <Button variant="secondary" disabled={busy} onClick={() => connectionAction(channel, "disconnect")}>
                    Disconnect
                  </Button>
                )}
                <Button
                  variant="secondary"
                  onClick={() => setEditing({ ...channel, approval_policy: "member_only", assigned_member_ids: [] })}
                >
                  Configure
                </Button>
              </div>
              {channel.subscriber_count != null && (
                <p className="studio-subtext">
                  {channel.subscriber_count.toLocaleString()} subscribers · {channel.video_count} videos
                </p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <section className="studio-card">
          <EmptyState
            title="No YouTube channels connected (Optional)"
            detail="You can use the full Title-to-Short pipeline and Manual MP4 Download without creating or connecting any channel."
            action={
              <Button variant="secondary" onClick={() => setShow(true)}>
                <Plus size={15} /> Create Optional Local Channel
              </Button>
            }
          />
        </section>
      )}

      <div className="callout-note" style={{ marginTop: 18 }}>
        <Radio size={17} />
        <span>
          <strong>Manual download always works.</strong> Connecting YouTube is completely optional and restricted to Owners/Admins.
        </span>
      </div>

      {editing && (
        <Modal title="Channel settings" onClose={() => setEditing(null)}>
          <form className="form-stack" onSubmit={configure}>
            <label>
              Approval policy
              <select
                value={editing.approval_policy}
                onChange={(e) => setEditing({ ...editing, approval_policy: e.target.value })}
              >
                <option value="member_only">Owner / Admin Approval</option>
              </select>
            </label>
            <label>
              Channel niche
              <input
                maxLength="160"
                value={editing.niche || ""}
                placeholder="Uses the assigned theme when blank"
                onChange={(e) => setEditing({ ...editing, niche: e.target.value })}
              />
            </label>
            <label>
              Optional historical reference URLs
              <textarea
                value={(editing.evergreen_source_urls || []).join("\n")}
                placeholder="Public primary/reference pages, one HTTPS URL per line"
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    evergreen_source_urls: e.target.value.split(/\r?\n/).filter(Boolean),
                  })
                }
              />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={!!editing.automatic_evergreen_fallback}
                onChange={(e) => setEditing({ ...editing, automatic_evergreen_fallback: e.target.checked })}
              />
              Automatically research verified historical stories when no usable news is found
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={!!editing.automatic_generation_enabled}
                onChange={(e) => setEditing({ ...editing, automatic_generation_enabled: e.target.checked })}
              />
              Prepare daily videos automatically
            </label>
            <label>
              Automatic video duration
              <select
                value={editing.generation_duration || 45}
                onChange={(e) => setEditing({ ...editing, generation_duration: Number(e.target.value) })}
              >
                {[30, 45, 60].map((n) => (
                  <option key={n} value={n}>{n} seconds</option>
                ))}
              </select>
            </label>
            <label>
              Daily preparation target
              <input
                type="number"
                min="1"
                max="3"
                value={editing.daily_video_target}
                onChange={(e) => setEditing({ ...editing, daily_video_target: e.target.value })}
              />
            </label>
            <label>
              Narration provider
              <select
                value={editing.tts_provider}
                onChange={(e) => setEditing({ ...editing, tts_provider: e.target.value })}
              >
                <option value="auto">Auto</option>
                <option value="local">Local</option>
                <option value="google">Google</option>
                <option value="elevenlabs">ElevenLabs</option>
              </select>
            </label>
            <LanguageSelect
              label="Default language"
              value={editing.default_language}
              onChange={(value) => setEditing({ ...editing, default_language: value })}
            />
            <label>
              Default narrator voice
              <input
                value={editing.default_voice}
                onChange={(e) => setEditing({ ...editing, default_voice: e.target.value })}
              />
            </label>
            <VoiceStyleSelect
              value={editing.voice_style || "auto"}
              onChange={(value) => setEditing({ ...editing, voice_style: value })}
            />
            <label>
              Brand accent
              <input
                type="color"
                value={editing.brand_color || "#61e8b6"}
                onChange={(e) => setEditing({ ...editing, brand_color: e.target.value })}
              />
            </label>
            <Button type="submit" loading={busy}>Save channel settings</Button>
          </form>
        </Modal>
      )}

      {show && (
        <Modal title="Create a local project channel" onClose={() => setShow(false)}>
          <form className="form-stack" onSubmit={submit}>
            <label>
              Channel name
              <input
                required
                minLength="2"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. My Sports Channel"
              />
            </label>
            <label>
              YouTube channel ID <span className="label-hint">Optional for local setup</span>
              <input
                value={form.youtube_channel_id}
                onChange={(e) => setForm({ ...form, youtube_channel_id: e.target.value })}
                placeholder="UC..."
              />
            </label>
            <label>
              Profile image URL
              <input
                type="url"
                value={form.profile_image_url}
                onChange={(e) => setForm({ ...form, profile_image_url: e.target.value })}
                placeholder="https://..."
              />
            </label>
            <label>
              Assign lead
              <select
                value={form.member_id}
                onChange={(e) => setForm({ ...form, member_id: e.target.value })}
              >
                <option value="">Workspace owner</option>
                {members
                  .filter((member) => member.role !== "OWNER" && member.active)
                  .map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.name} · {member.role}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Default voice
              <select
                value={form.default_voice}
                onChange={(e) => setForm({ ...form, default_voice: e.target.value })}
              >
                <option value="en-US">English narrator</option>
                <option value="es-ES">Spanish narrator</option>
                <option value="fr-FR">French narrator</option>
              </select>
            </label>
            <div className="form-row">
              <LanguageSelect
                label="Default language"
                value={form.default_language}
                onChange={(value) => setForm({ ...form, default_language: value })}
              />
              <label>
                Daily video target
                <input
                  type="number"
                  min="1"
                  max="3"
                  value={form.daily_video_target}
                  onChange={(e) => setForm({ ...form, daily_video_target: e.target.value })}
                />
              </label>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.approval_required}
                onChange={(e) => setForm({ ...form, approval_required: e.target.checked })}
              />
              Require approval before download/publishing
            </label>
            <div className="modal-actions">
              <Button type="button" variant="secondary" onClick={() => setShow(false)}>
                Cancel
              </Button>
              <Button type="submit">
                <Plus size={15} /> Add channel
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
