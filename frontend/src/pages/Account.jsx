import { useEffect, useState } from "react";
import { Check, Copy, Link2, Lock, Mail, ShieldCheck, User } from "lucide-react";
import { api } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

export default function Account() {
  const [me, setMe] = useState(null);
  const [error, setError] = useState("");
  const [copiedLink, setCopiedLink] = useState(false);
  const registerUrl = `${window.location.origin}/register`;

  function copyRegisterLink() {
    navigator.clipboard?.writeText(registerUrl).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2500);
    }).catch(() => {});
  }

  useEffect(() => {
    api("/auth/me")
      .then(setMe)
      .catch((err) => setError(err.message));
  }, []);

  if (error && !me) return <Notice>{error}</Notice>;
  if (!me) return <Loading />;

  return (
    <div>
      <PageHeader
        eyebrow="ACCOUNT & STUDIO"
        title="Account Settings"
        description="Your studio login details and private workspace status."
      />

      {error && <Notice>{error}</Notice>}

      <div className="studio-grid-equal">
        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <User size={17} />
              <span>Profile Details</span>
            </h2>
            <span className="studio-role-chip admin">STUDIO ACCOUNT</span>
          </div>

          <div style={{ display: "grid", gap: 12 }}>
            <div className="studio-role-card">
              <strong>
                <User size={14} />
                <span>Full Name</span>
              </strong>
              <p>{me.name || me.user?.name || "Studio User"}</p>
            </div>
            <div className="studio-role-card">
              <strong>
                <Mail size={14} />
                <span>Email Address</span>
              </strong>
              <p>{me.email || me.user?.email || "—"}</p>
            </div>
            <div className="studio-role-card">
              <strong>
                <Lock size={14} />
                <span>Private Workspace</span>
              </strong>
              <p>{me.workspace_name || me.workspace?.name || me.workspace_id || "My Studio"}</p>
            </div>
          </div>
        </section>

        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <ShieldCheck size={17} />
              <span>Workspace Capabilities</span>
            </h2>
          </div>

          <div className="studio-role-card" style={{ marginBottom: 12 }}>
            <strong>Full Studio Access (Isolated Workspace)</strong>
            <p>
              Your videos, drafts, Celebrity Folder clips, and AI settings stay strictly inside your own private account.
            </p>
          </div>

          <div style={{ display: "grid", gap: 8, fontSize: 12.5, color: "var(--text-muted)" }}>
            <div>• Create Shorts from Title: <strong style={{ color: "var(--text)" }}>Enabled</strong></div>
            <div>• Fast Celebrity Folder Sync: <strong style={{ color: "var(--text)" }}>Enabled</strong></div>
            <div>• Download Final 9:16 MP4: <strong style={{ color: "var(--text)" }}>Direct &amp; Instant</strong></div>
            <div>• Delete Any Video or Draft: <strong style={{ color: "var(--text)" }}>Enabled</strong></div>
          </div>

          <div className="studio-role-card" style={{ marginTop: 14 }}>
            <strong>
              <Link2 size={14} />
              <span>Share Signup Link (Separate Workspace)</span>
            </strong>
            <p style={{ marginBottom: 10 }}>
              Share this link so anyone can register with their own email and password. Each person gets their own completely isolated studio and drafts.
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <input
                readOnly
                aria-label="Shareable registration link"
                value={registerUrl}
                onFocus={(e) => e.target.select()}
                style={{ flex: 1, minWidth: 220, fontSize: 12.5, padding: "8px 10px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
              />
              <Button variant="secondary" type="button" onClick={copyRegisterLink}>
                {copiedLink ? <Check size={14} /> : <Copy size={14} />}
                <span>{copiedLink ? "Link Copied!" : "Copy Signup Link"}</span>
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
