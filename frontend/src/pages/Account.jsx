import { useEffect, useState } from "react";
import { Lock, Mail, ShieldCheck, User } from "lucide-react";
import { api } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Loading, Notice } from "../components/UI";

const ROLE_DESCRIPTION = {
  OWNER: "Full control across your private workspace: employee approvals, Celebrity Vault management, exports, and creating isolated partner accounts.",
  ADMIN: "Workspace Administrator: full access inside this private workspace, completely isolated from any other owner's workspace.",
  MEMBER: "Employee Creator: create AI Shorts from titles, use the workspace Celebrity Folder in scenes, submit drafts for Owner approval, and download your approved videos.",
  EDITOR: "Employee Creator: create AI Shorts from titles, use the workspace Celebrity Folder in scenes, submit drafts for Owner approval, and download your approved videos.",
  VIEWER: "Read-only observer in this workspace.",
};

export default function Account() {
  const [me, setMe] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/auth/me")
      .then(setMe)
      .catch((err) => setError(err.message));
  }, []);

  if (error && !me) return <Notice>{error}</Notice>;
  if (!me) return <Loading />;

  const role = me.role || localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);

  return (
    <div>
      <PageHeader
        eyebrow="PROFILE & PERMISSIONS"
        title="Account Settings"
        description="Your studio login details, active workspace scope, and role permissions."
      />

      {error && <Notice>{error}</Notice>}

      <div className="studio-grid-equal">
        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <User size={17} />
              <span>Profile Details</span>
            </h2>
            <span className={`studio-role-chip ${isAdmin ? "admin" : "member"}`}>{role}</span>
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
                <span>Active Workspace</span>
              </strong>
              <p>{me.workspace_name || me.workspace?.name || me.workspace_id || "Private Studio Workspace"}</p>
            </div>
          </div>
        </section>

        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <ShieldCheck size={17} />
              <span>Your Role Permissions</span>
            </h2>
          </div>

          <div className="studio-role-card" style={{ marginBottom: 12 }}>
            <strong>{role === "OWNER" ? "Workspace Owner" : role === "ADMIN" ? "Isolated Workspace Admin" : "Employee Creator"}</strong>
            <p>{ROLE_DESCRIPTION[role] || ROLE_DESCRIPTION.MEMBER}</p>
          </div>

          <div style={{ display: "grid", gap: 8, fontSize: 12.5, color: "var(--text-muted)" }}>
            <div>• Create Shorts from Title: <strong style={{ color: "var(--text)" }}>Allowed</strong></div>
            <div>• Browse &amp; Use Celebrity Vault: <strong style={{ color: "var(--text)" }}>Allowed</strong></div>
            <div>
              • Download Final MP4:{" "}
              <strong style={{ color: "var(--text)" }}>
                {isAdmin ? "Immediate" : "Unlocked after Owner Approval"}
              </strong>
            </div>
            <div>
              • Delete Unsubmitted Drafts:{" "}
              <strong style={{ color: "var(--text)" }}>Allowed (own unsubmitted/rejected drafts)</strong>
            </div>
            <div>
              • Approve Videos, Delete Submitted/Approved Videos &amp; Manage Team Roles:{" "}
              <strong style={{ color: "var(--text)" }}>{isAdmin ? "Allowed" : "Restricted to Owner/Admin"}</strong>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
