import AppearanceSelector from "../components/AppearanceSelector";
import BrandLogo from "../components/BrandLogo";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, LockKeyhole, ShieldCheck, UserPlus } from "lucide-react";
import { api } from "../services/api";
import { Button, Loading, Notice } from "../components/UI";

function formatInviteRole(invite) {
  if (!invite) return "Studio Member";
  if (invite.isolated) return "Isolated Workspace Owner (Private Workspace)";
  if (invite.role === "ADMIN") return "Workspace Admin";
  return "Employee Creator";
}

export default function Join({ onLogin }) {
  const [params] = useSearchParams();
  const token = (params.get("invite") || params.get("token") || "").trim();
  const navigate = useNavigate();

  const [invite, setInvite] = useState(null);
  const [checking, setChecking] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      setChecking(false);
      setLoadError("No invite token found in this link. Ask your workspace owner for a fresh shareable link.");
      return;
    }
    let active = true;
    setChecking(true);
    setLoadError("");
    api(`/invites/${encodeURIComponent(token)}`)
      .then((data) => {
        if (!active) return;
        setInvite(data);
        if (data.target_email) setEmail(data.target_email);
      })
      .catch((err) => {
        if (active) setLoadError(err.message);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  async function submitAccept(e) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const result = await api("/invites/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          name: name.trim(),
          email: email.trim(),
          password,
        }),
      });
      onLogin(result);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-appearance">
        <AppearanceSelector />
      </div>

      <div className="login-visual">
        <div className="login-brand">
          <BrandLogo />
        </div>
        <div className="visual-copy">
          <span className="pill light-pill">INVITED STUDIO ACCESS</span>
          <h1>
            Create your account
            <br />
            <em>in seconds.</em>
          </h1>
          <p>
            Join your creative studio workspace or launch your own isolated private workspace using this verified invite link.
          </p>
          <div className="visual-preview">
            <div className="preview-screen">
              <div className="preview-stars">✦ &nbsp; ✧ &nbsp; ✦</div>
              <span>AI SHORTS STUDIO</span>
              <strong>{invite ? formatInviteRole(invite) : "Verified Invitation"}</strong>
              <div className="preview-controls">
                <i />
                <i />
                <i />
              </div>
            </div>
            <div className="preview-note">
              <span className="live-dot" /> Private login · Choose your own password
            </div>
          </div>
        </div>
        <div className="login-footer">Set your details once and sign in anytime.</div>
      </div>

      <div className="login-panel">
        <div className="login-form-wrap">
          <span className="mobile-brand">
            <BrandLogo />
          </span>
          <div className="login-icon">
            <UserPlus size={21} />
          </div>

          <div className="eyebrow">WORKSPACE INVITATION</div>
          <h2>Accept Invite &amp; Join</h2>

          {checking ? (
            <Loading />
          ) : loadError ? (
            <>
              <Notice>{loadError}</Notice>
              <Link to="/login" className="text-link" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 10 }}>
                <ArrowLeft size={14} /> Go to Sign In
              </Link>
            </>
          ) : (
            <>
              <div className="studio-role-card" style={{ marginBottom: 14 }}>
                <strong style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <ShieldCheck size={15} />
                  <span>{formatInviteRole(invite)}</span>
                </strong>
                <p style={{ marginTop: 4 }}>
                  {invite?.isolated
                    ? "You will get your own 100% isolated private workspace — zero shared data with anyone else."
                    : `Workspace: ${invite?.workspace_name || "Creator Studio"}.${invite?.label ? ` Note: ${invite.label}` : ""}`}
                </p>
              </div>

              <form onSubmit={submitAccept}>
                <label>
                  Full name
                  <input
                    required
                    minLength={2}
                    maxLength={120}
                    placeholder="Your name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>

                <label>
                  Email address
                  <input
                    type="email"
                    required
                    readOnly={Boolean(invite?.target_email)}
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>

                <label>
                  Choose password <span className="label-hint">(min. 8 characters)</span>
                  <div className="password-input">
                    <input
                      type={show ? "text" : "password"}
                      required
                      minLength={8}
                      maxLength={128}
                      autoComplete="new-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                    <button
                      type="button"
                      aria-label="Toggle password"
                      onClick={() => setShow(!show)}
                    >
                      {show ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </label>

                <label>
                  Confirm password
                  <input
                    type={show ? "text" : "password"}
                    required
                    minLength={8}
                    maxLength={128}
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                </label>

                <Notice>{error}</Notice>

                <Button loading={busy} type="submit" className="full-button">
                  Create Account &amp; Enter Studio <span>→</span>
                </Button>
              </form>

              <p style={{ marginTop: 12 }}>
                Already have an account?{" "}
                <Link to="/login" className="text-link">
                  Sign in here
                </Link>
              </p>
            </>
          )}

          <div className="secure-note">
            <LockKeyhole size={13} /> Your workspace is private and secure
          </div>
        </div>
        <div className="login-legal">
          © 2026 AI Shorts <span>Built for creators, with care.</span>
        </div>
      </div>
    </div>
  );
}
