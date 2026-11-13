import { useEffect, useState } from "react";
import {
  Check,
  Copy,
  KeyRound,
  Link2,
  Lock,
  Shield,
  ShieldAlert,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  UserX,
} from "lucide-react";
import { api } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

const ROLE_LABELS = {
  OWNER: "Workspace Owner",
  ADMIN: "Admin / Workspace Owner",
  MEMBER: "Employee (Creator Only)",
  EDITOR: "Employee (Creator Only)",
  VIEWER: "Employee (Creator Only)",
};

function formatRoleBadge(role) {
  if (role === "OWNER") return "Owner";
  if (role === "ADMIN") return "Admin";
  return "Employee";
}

export default function Team() {
  const initialRole = localStorage.getItem("role") || "MEMBER";
  const [me, setMe] = useState(null);
  const [members, setMembers] = useState(null);
  const [invites, setInvites] = useState([]);
  const [audit, setAudit] = useState([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  const [rowBusyId, setRowBusyId] = useState("");
  const [inviteCreds, setInviteCreds] = useState(null);
  const [shareLinkInfo, setShareLinkInfo] = useState(null);
  const [copiedCreds, setCopiedCreds] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [inviteMode, setInviteMode] = useState("link"); // "link" | "direct"
  const [linkForm, setLinkForm] = useState({
    accountType: "employee", // "employee" | "isolated_friend" | "co_admin"
    label: "",
    target_email: "",
    expires_in_days: 7,
  });
  const [directForm, setDirectForm] = useState({
    name: "",
    email: "",
    role: "MEMBER",
  });

  async function loadTeam() {
    try {
      const authMe = await api("/auth/me");
      setMe(authMe);
      const role = authMe?.role || initialRole;
      if (!["OWNER", "ADMIN"].includes(role)) {
        setMembers([]);
        setInvites([]);
        setAudit([]);
        return;
      }
      const [memberRows, inviteRows, auditRows] = await Promise.all([
        api("/members"),
        api("/team/invites"),
        api("/members/audit"),
      ]);
      setMembers(memberRows);
      setInvites(inviteRows || []);
      setAudit(auditRows || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadTeam();
  }, []);

  async function handleGenerateLink(e) {
    e.preventDefault();
    setLinkBusy(true);
    setError("");
    setStatus("");
    setShareLinkInfo(null);
    setCopiedLink(false);
    try {
      const payload = {
        role: linkForm.accountType === "employee" ? "MEMBER" : "ADMIN",
        isolated: linkForm.accountType === "isolated_friend",
        label: linkForm.label.trim(),
        expires_in_days: Number(linkForm.expires_in_days || 7),
        ...(linkForm.target_email.trim() ? { target_email: linkForm.target_email.trim() } : {}),
      };
      const created = await api("/team/invite-links", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const fullUrl = `${window.location.origin}${created.invite_path}`;
      setShareLinkInfo({ ...created, fullUrl });
      setLinkForm({ ...linkForm, label: "", target_email: "" });
      setStatus("Shareable invite link generated! Send this link so they can set their own name & password.");
      await loadTeam();
    } catch (err) {
      setError(err.message);
    } finally {
      setLinkBusy(false);
    }
  }

  async function revokeLink(inviteId) {
    setRowBusyId(inviteId);
    setError("");
    try {
      await api(`/team/invites/${inviteId}`, { method: "DELETE" });
      setStatus("Invite link revoked.");
      await loadTeam();
    } catch (err) {
      setError(err.message);
    } finally {
      setRowBusyId("");
    }
  }

  async function handleDirectInvite(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setStatus("");
    setInviteCreds(null);
    setCopiedCreds(false);
    try {
      const created = await api("/team/invite", {
        method: "POST",
        body: JSON.stringify(directForm),
      });
      setInviteCreds(created);
      setDirectForm({ name: "", email: "", role: "MEMBER" });
      setStatus(
        created.isolated
          ? `Created separate isolated workspace "${created.workspace_name}" for ${created.email}.`
          : `Added Employee ${created.name} to your workspace.`
      );
      await loadTeam();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRoleChange(memberId, newRole) {
    setRowBusyId(memberId);
    setError("");
    setStatus("");
    try {
      await api(`/team/members/${memberId}/role`, {
        method: "PUT",
        body: JSON.stringify({ role: newRole }),
      });
      setStatus("Updated member role.");
      await loadTeam();
    } catch (err) {
      setError(err.message);
    } finally {
      setRowBusyId("");
    }
  }

  async function toggleMemberField(member, patch, message) {
    setRowBusyId(member.id);
    setError("");
    setStatus("");
    try {
      await api(`/members/${member.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setStatus(message);
      await loadTeam();
    } catch (err) {
      setError(err.message);
    } finally {
      setRowBusyId("");
    }
  }

  async function copyShareLink() {
    if (!shareLinkInfo?.fullUrl) return;
    try {
      await navigator.clipboard.writeText(shareLinkInfo.fullUrl);
      setCopiedLink(true);
    } catch {
      setCopiedLink(false);
    }
  }

  async function copyCredentials() {
    if (!inviteCreds) return;
    const text = [
      `Studio Login: ${window.location.origin}/login`,
      `Workspace: ${inviteCreds.workspace_name}`,
      `Role: ${formatRoleBadge(inviteCreds.role)}`,
      `Email: ${inviteCreds.email}`,
      inviteCreds.temporary_password
        ? `Temporary Password: ${inviteCreds.temporary_password}`
        : `Password: Existing account password`,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopiedCreds(true);
    } catch {
      setCopiedCreds(false);
    }
  }

  if (error && !me) {
    return <Notice>{error}</Notice>;
  }
  if (!me || members === null) {
    return <Loading />;
  }

  const currentRole = me?.role || initialRole;
  const isAdmin = ["OWNER", "ADMIN"].includes(currentRole);
  const currentUserId = me?.id || me?.user?.id;
  const selfMember = members.find((m) => m.user_id === currentUserId);
  const canAppointAdmin = currentRole === "OWNER" || Boolean(selfMember?.can_manage_admins);

  return (
    <div>
      <PageHeader
        eyebrow="WORKSPACE ACCESS, LINKS & ROLES"
        title="Team & Shareable Invites"
        description="Assign workspace roles or share a secure signup link to invite Employees or create a 100% isolated Friend workspace."
      />

      {error && <Notice>{error}</Notice>}
      {status && <Notice type="success">{status}</Notice>}

      <div className="studio-grid-3" style={{ marginBottom: 20 }}>
        <div className="studio-role-card">
          <strong>
            <Shield size={15} />
            <span>Owner (Main Control)</span>
          </strong>
          <p>
            Full control across your workspace, approvals, Celebrity Vault management, and creating isolated Friend links.
          </p>
        </div>
        <div className="studio-role-card">
          <strong>
            <Lock size={15} />
            <span>Admin / Isolated Friend</span>
          </strong>
          <p>
            Gets the exact same full Studio interface inside their workspace. Isolated Friend accounts never see or share data with your workspace.
          </p>
        </div>
        <div className="studio-role-card">
          <strong>
            <Users size={15} />
            <span>Employee (Creator Only)</span>
          </strong>
          <p>
            Sees the same Studio layout cleanly, creates Shorts from Title using the Celebrity Folder, deletes own unsubmitted drafts, and downloads MP4s once Owner approves.
          </p>
        </div>
      </div>

      {!isAdmin && (
        <section className="studio-card" style={{ marginBottom: 20 }}>
          <div className="studio-card-head">
            <h2>
              <Lock size={17} />
              <span>Team Management Locked for Employee Accounts</span>
            </h2>
            <span className="studio-lock-pill">
              <Lock size={12} />
              <span>Owner / Admin Only</span>
            </span>
          </div>
          <p className="studio-subtext">
            You are signed in as <strong>{me.name || me.email}</strong> (<strong>Employee</strong> in <strong>{me.workspace_name || "Workspace"}</strong>). You can create Shorts from Title, pick Celebrity Folder visuals, and download approved MP4s. Ask your Owner/Admin if you need an invite link shared or a role change.
          </p>
        </section>
      )}

      {shareLinkInfo && (
        <section className="studio-cred-banner" role="status">
          <div className="studio-card-head" style={{ marginBottom: 6 }}>
            <h3>
              <Link2 size={17} />
              <span>
                {shareLinkInfo.isolated
                  ? "Shareable Isolated Friend Link Ready"
                  : "Shareable Workspace Invite Link Ready"}
              </span>
            </h3>
            <Button onClick={copyShareLink}>
              {copiedLink ? <Check size={14} /> : <Copy size={14} />}
              <span>{copiedLink ? "Link Copied!" : "Copy Invite Link"}</span>
            </Button>
          </div>
          <div className="studio-cred-item" style={{ marginBottom: 8 }}>
            <span>Share This URL (Friend/Employee sets their own Name, Email &amp; Password)</span>
            <code style={{ wordBreak: "break-all" }}>{shareLinkInfo.fullUrl}</code>
          </div>
          <p className="studio-subtext">
            Access type: <strong>{shareLinkInfo.isolated ? "100% Isolated Friend Workspace (Admin)" : formatRoleBadge(shareLinkInfo.role)}</strong> · Expires: {new Date(shareLinkInfo.expires_at).toLocaleDateString()}
          </p>
        </section>
      )}

      {inviteCreds && (
        <section className="studio-cred-banner" role="status">
          <div className="studio-card-head" style={{ marginBottom: 4 }}>
            <h3>
              <KeyRound size={17} />
              <span>
                {inviteCreds.isolated
                  ? "Isolated Friend Account Ready — Share Login Details"
                  : "Employee Added — Share Login Details"}
              </span>
            </h3>
            <Button variant="secondary" onClick={copyCredentials}>
              {copiedCreds ? <Check size={14} /> : <Copy size={14} />}
              <span>{copiedCreds ? "Copied!" : "Copy Login Details"}</span>
            </Button>
          </div>
          <div className="studio-cred-grid">
            <div className="studio-cred-item">
              <span>Account Email</span>
              <code>{inviteCreds.email}</code>
            </div>
            <div className="studio-cred-item">
              <span>Temporary Password</span>
              <code>{inviteCreds.temporary_password || "Existing password unchanged"}</code>
            </div>
            <div className="studio-cred-item">
              <span>Workspace Scope</span>
              <code>
                {inviteCreds.workspace_name} ({inviteCreds.isolated ? "100% Isolated" : "Team Member"})
              </code>
            </div>
          </div>
        </section>
      )}

      <div className="studio-grid-2">
        <section className="studio-card">
          <div className="studio-card-head">
            <div>
              <h2>
                <Users size={17} />
                <span>Members in This Workspace ({isAdmin ? members.length : 1})</span>
              </h2>
              <p className="studio-subtext">
                Isolated Friend accounts get their own private workspace and never appear inside your employee roster.
              </p>
            </div>
          </div>

          <div className="table-wrap">
            <table className="studio-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {isAdmin ? (
                  members.map((m) => {
                    const isSelf = m.user_id === currentUserId;
                    const isOwner = m.role === "OWNER";
                    const canEditRole =
                      !isOwner &&
                      !isSelf &&
                      (currentRole === "OWNER" || (canAppointAdmin && m.role !== "ADMIN"));
                    const canToggleActive =
                      !isOwner &&
                      !isSelf &&
                      (currentRole === "OWNER" || m.role !== "ADMIN");

                    return (
                      <tr key={m.id}>
                        <td>
                          <div className="member-cell">
                            <span className="member-avatar">
                              {(m.name || "?").slice(0, 1).toUpperCase()}
                            </span>
                            <span>
                              <strong>
                                {m.name} {isSelf ? "(You)" : ""}
                              </strong>
                              <small>{m.email}</small>
                            </span>
                          </div>
                        </td>
                        <td>
                          {canEditRole ? (
                            <select
                              aria-label={`Role for ${m.name}`}
                              className="studio-select-inline"
                              disabled={rowBusyId === m.id}
                              value={["EDITOR", "VIEWER"].includes(m.role) ? "MEMBER" : m.role}
                              onChange={(e) => handleRoleChange(m.id, e.target.value)}
                            >
                              <option value="MEMBER">Employee (Create + Approved Download)</option>
                              {canAppointAdmin && (
                                <option value="ADMIN">Admin (Full Workspace Access)</option>
                              )}
                            </select>
                          ) : (
                            <span className={`role-pill ${isOwner ? "role-owner" : ""}`}>
                              {ROLE_LABELS[m.role] || m.role}
                            </span>
                          )}
                        </td>
                        <td>
                          <span className={`studio-badge ${m.active ? "active" : "inactive"}`}>
                            {m.active ? "Active" : "Suspended"}
                          </span>
                        </td>
                        <td>
                          <div className="studio-action-row">
                            {canToggleActive && (
                              <Button
                                variant="secondary"
                                loading={rowBusyId === m.id}
                                onClick={() =>
                                  toggleMemberField(
                                    m,
                                    { active: !m.active },
                                    m.active
                                      ? `Deactivated ${m.name}.`
                                      : `Reactivated ${m.name}.`
                                  )
                                }
                              >
                                {m.active ? <UserX size={13} /> : <UserCheck size={13} />}
                                <span>{m.active ? "Deactivate" : "Activate"}</span>
                              </Button>
                            )}
                            {currentRole === "OWNER" && m.role === "ADMIN" && !isSelf && (
                              <Button
                                variant="secondary"
                                loading={rowBusyId === m.id}
                                onClick={() =>
                                  toggleMemberField(
                                    m,
                                    { can_manage_admins: !m.can_manage_admins },
                                    m.can_manage_admins
                                      ? `Removed admin delegation from ${m.name}.`
                                      : `Delegated admin management to ${m.name}.`
                                  )
                                }
                              >
                                <ShieldAlert size={13} />
                                <span>{m.can_manage_admins ? "Revoke Admin" : "Delegate Admin"}</span>
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td>
                      <div className="member-cell">
                        <span className="member-avatar">
                          {(me.name || "?").slice(0, 1).toUpperCase()}
                        </span>
                        <span>
                          <strong>{me.name} (You)</strong>
                          <small>{me.email}</small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <span className="role-pill">{ROLE_LABELS[currentRole] || "Employee"}</span>
                    </td>
                    <td>
                      <span className="studio-badge active">Active</span>
                    </td>
                    <td>
                      <span className="studio-lock-pill">
                        <Lock size={12} />
                        <span>Locked</span>
                      </span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="studio-card">
          <div className="studio-card-head">
            <div>
              <h2>
                {inviteMode === "link" ? <Link2 size={17} /> : <UserPlus size={17} />}
                <span>Add Member or Share Invite Link</span>
              </h2>
              <p className="studio-subtext">
                Generate a link anyone can open to set up their own account, or create an account immediately.
              </p>
            </div>
            {!isAdmin && (
              <span className="studio-lock-pill">
                <Lock size={12} />
                <span>Locked</span>
              </span>
            )}
          </div>

          <div className="vault-pill-group" style={{ marginBottom: 14 }}>
            <button
              type="button"
              className={`filter-pill ${inviteMode === "link" ? "active" : ""}`}
              onClick={() => setInviteMode("link")}
            >
              <Link2 size={13} style={{ marginRight: 5, verticalAlign: "middle" }} />
              Shareable Invite Link
            </button>
            <button
              type="button"
              className={`filter-pill ${inviteMode === "direct" ? "active" : ""}`}
              onClick={() => setInviteMode("direct")}
            >
              <KeyRound size={13} style={{ marginRight: 5, verticalAlign: "middle" }} />
              Create With Temp Password
            </button>
          </div>

          {inviteMode === "link" ? (
            <form className="form-stack" onSubmit={handleGenerateLink}>
              <div className="studio-field">
                <label className="studio-label" htmlFor="link-account-type">Link Access Type</label>
                <select
                  id="link-account-type"
                  disabled={!isAdmin}
                  value={linkForm.accountType}
                  onChange={(e) => setLinkForm({ ...linkForm, accountType: e.target.value })}
                >
                  <option value="employee">
                    Employee Link (Join Your Workspace — Create Shorts &amp; Approved Download)
                  </option>
                  {currentRole === "OWNER" && (
                    <option value="isolated_friend">
                      Isolated Friend Link (Creates 100% Separate Private Workspace)
                    </option>
                  )}
                  {canAppointAdmin && (
                    <option value="co_admin">
                      Admin Link (Full Access Inside Your Workspace)
                    </option>
                  )}
                </select>
              </div>

              <div className="form-row">
                <div className="studio-field">
                  <label className="studio-label" htmlFor="link-label">Optional Note / Label</label>
                  <input
                    id="link-label"
                    disabled={!isAdmin}
                    placeholder="e.g. Video Editor Invite"
                    value={linkForm.label}
                    onChange={(e) => setLinkForm({ ...linkForm, label: e.target.value })}
                  />
                </div>
                <div className="studio-field">
                  <label className="studio-label" htmlFor="link-days">Expires In</label>
                  <select
                    id="link-days"
                    disabled={!isAdmin}
                    value={linkForm.expires_in_days}
                    onChange={(e) => setLinkForm({ ...linkForm, expires_in_days: Number(e.target.value) })}
                  >
                    <option value={1}>24 Hours</option>
                    <option value={7}>7 Days</option>
                    <option value={14}>14 Days</option>
                    <option value={30}>30 Days</option>
                  </select>
                </div>
              </div>

              <div className="studio-field">
                <label className="studio-label" htmlFor="link-email">
                  Lock to Specific Email (optional — leave blank so anyone with link can enter their email)
                </label>
                <input
                  id="link-email"
                  type="email"
                  disabled={!isAdmin}
                  placeholder="Optional: restrict link to one email"
                  value={linkForm.target_email}
                  onChange={(e) => setLinkForm({ ...linkForm, target_email: e.target.value })}
                />
              </div>

              <Button type="submit" loading={linkBusy} disabled={!isAdmin} style={{ width: "100%" }}>
                {!isAdmin && <Lock size={14} />}
                <Link2 size={15} />
                <span>{isAdmin ? "Generate Shareable Invite Link" : "Invite Links Locked to Owner/Admin"}</span>
              </Button>
            </form>
          ) : (
            <form className="form-stack" onSubmit={handleDirectInvite}>
              <div className="studio-field">
                <label className="studio-label" htmlFor="invite-mode">Account Type &amp; Isolation</label>
                <select
                  id="invite-mode"
                  disabled={!isAdmin}
                  value={directForm.role}
                  onChange={(e) => setDirectForm({ ...directForm, role: e.target.value })}
                >
                  <option value="MEMBER">
                    Employee in This Workspace (Title Shorts + Approved Downloads Only)
                  </option>
                  {currentRole === "OWNER" && (
                    <option value="ADMIN">
                      Separate Friend Owner Account (100% Isolated Private Workspace)
                    </option>
                  )}
                </select>
              </div>

              <div className="studio-field">
                <label className="studio-label" htmlFor="invite-name">Full Name</label>
                <input
                  id="invite-name"
                  required
                  minLength={2}
                  disabled={!isAdmin}
                  placeholder={directForm.role === "ADMIN" ? "Friend's Name" : "Employee Name"}
                  value={directForm.name}
                  onChange={(e) => setDirectForm({ ...directForm, name: e.target.value })}
                />
              </div>

              <div className="studio-field">
                <label className="studio-label" htmlFor="invite-email">Login Email Address</label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  disabled={!isAdmin}
                  placeholder="name@example.com"
                  value={directForm.email}
                  onChange={(e) => setDirectForm({ ...directForm, email: e.target.value })}
                />
              </div>

              <Button type="submit" loading={busy} disabled={!isAdmin} style={{ width: "100%" }}>
                {!isAdmin && <Lock size={14} />}
                <UserPlus size={15} />
                <span>
                  {!isAdmin
                    ? "Inviting Locked to Owner/Admin"
                    : directForm.role === "ADMIN"
                    ? "Create Isolated Friend Account"
                    : "Invite Employee"}
                </span>
              </Button>
            </form>
          )}
        </section>
      </div>

      {isAdmin && (
        <section className="studio-card" style={{ marginTop: 18 }}>
          <div className="studio-card-head">
            <h2>Shareable Invite Links History</h2>
            <span className="count-chip">{invites.length}</span>
          </div>
          {invites.length === 0 ? (
            <p className="studio-subtext">
              No shareable invite links generated yet. Use the form above to generate one and share it.
            </p>
          ) : (
            <div className="table-wrap">
              <table className="studio-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Label / Email Lock</th>
                    <th>Status</th>
                    <th>Expires</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {invites.map((inv) => (
                    <tr key={inv.id}>
                      <td>
                        <strong>
                          {inv.isolated ? "Isolated Friend Workspace" : formatRoleBadge(inv.role)}
                        </strong>
                      </td>
                      <td>
                        {inv.label || "General invite"}
                        {inv.target_email ? ` · ${inv.target_email}` : " · Open link"}
                      </td>
                      <td>
                        <span
                          className={`studio-badge ${
                            inv.status === "active"
                              ? "connected"
                              : inv.status === "used"
                              ? "approved"
                              : "inactive"
                          }`}
                        >
                          {inv.status}
                        </span>
                      </td>
                      <td>{new Date(inv.expires_at).toLocaleDateString()}</td>
                      <td>
                        {inv.status === "active" && (
                          <Button
                            variant="danger"
                            loading={rowBusyId === inv.id}
                            onClick={() => revokeLink(inv.id)}
                          >
                            <Trash2 size={13} />
                            <span>Revoke</span>
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {isAdmin && (
        <section className="studio-card" style={{ marginTop: 18 }}>
          <div className="studio-card-head">
            <h2>Workspace Role &amp; Security Audit Log</h2>
            <span className="count-chip">{audit.length}</span>
          </div>
          {audit.length === 0 ? (
            <p className="studio-subtext">No administrative role changes recorded yet in this workspace.</p>
          ) : (
            <div className="table-wrap">
              <table className="studio-table">
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Details</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.slice(0, 20).map((entry) => (
                    <tr key={entry.id}>
                      <td>
                        <span className="mood-tag">{entry.action}</span>
                      </td>
                      <td>{JSON.stringify(entry.details)}</td>
                      <td>{new Date(entry.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
