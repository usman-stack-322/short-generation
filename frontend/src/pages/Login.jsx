import AppearanceSelector from "../components/AppearanceSelector";
import BrandLogo from "../components/BrandLogo";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, KeyRound, LockKeyhole, UserPlus } from "lucide-react";
import { api } from "../services/api";
import { Button, Notice } from "../components/UI";

export default function Login({ onLogin, initialMode = "login" }) {
  const [searchParams] = useSearchParams();
  const queryMode = searchParams.get("mode");
  const startMode = queryMode === "register" ? "register" : initialMode;
  const [mode, setMode] = useState(startMode); // "login" | "register" | "forgot" | "reset"
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);
  const navigate = useNavigate();

  function switchMode(nextMode) {
    setMode(nextMode);
    setError("");
    if (nextMode === "login" || nextMode === "register") {
      setInfo("");
      setCode("");
      setNewPassword("");
      setConfirmPassword("");
    }
  }

  async function submitRegister(event) {
    event.preventDefault();
    setError("");
    setInfo("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters long.");
      return;
    }
    setLoading(true);
    try {
      const result = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), email, password }),
      });
      onLogin(result);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitLogin(event) {
    event.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      const result = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      onLogin(result);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitForgot(event) {
    event.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      const result = await api("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setInfo(
        result.message ||
          "If an active account matches that email, a 6-digit verification code has been sent."
      );
      setMode("reset");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitReset(event) {
    event.preventDefault();
    setError("");
    if (newPassword.length < 10) {
      setError("New password must be at least 10 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      const result = await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          email,
          code: code.trim(),
          new_password: newPassword,
        }),
      });
      onLogin(result);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
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
          <span className="pill light-pill">THE SHORT-FORM STUDIO</span>
          <h1>
            From big ideas
            <br />
            to <em>short stories.</em>
          </h1>
          <p>
            Research, write, and produce your next great Short — all in one
            creative workspace.
          </p>
          <div className="visual-preview">
            <div className="preview-screen">
              <div className="preview-stars">✦ &nbsp; ✧ &nbsp; ✦</div>
              <span>YOUR NEXT SHORT</span>
              <strong>starts here.</strong>
              <div className="preview-controls">
                <i />
                <i />
                <i />
              </div>
            </div>
            <div className="preview-note">
              <span className="live-dot" /> Creative momentum, in one place
            </div>
          </div>
        </div>
        <div className="login-footer">A little more story in every scroll.</div>
      </div>

      <div className="login-panel">
        <div className="login-form-wrap">
          <span className="mobile-brand">
            <BrandLogo />
          </span>
          {localStorage.getItem("token") && (
            <Notice type="success">
              You are already signed in. Creating an account below will open your own brand-new isolated workspace, or{" "}
              <button
                type="button"
                className="inline-link"
                onClick={() => navigate("/")}
                style={{ fontWeight: 600 }}
              >
                return to your studio
              </button>
              .
            </Notice>
          )}
          <div className="login-icon">
            {mode === "login" ? (
              <LockKeyhole size={21} />
            ) : mode === "register" ? (
              <UserPlus size={21} />
            ) : (
              <KeyRound size={21} />
            )}
          </div>

          {(mode === "login" || mode === "register") && (
            <div className="auth-mode-tabs" role="tablist" aria-label="Account mode">
              <button
                type="button"
                role="tab"
                aria-selected={mode === "login"}
                className={mode === "login" ? "active" : ""}
                onClick={() => switchMode("login")}
              >
                Sign in
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "register"}
                className={mode === "register" ? "active" : ""}
                onClick={() => switchMode("register")}
              >
                Create account
              </button>
            </div>
          )}

          {mode === "login" && (
            <>
              <div className="eyebrow">WELCOME BACK</div>
              <h2>Sign in to your studio</h2>
              <p className="muted">Your next story is only a few clicks away.</p>
              <form onSubmit={submitLogin}>
                <label>
                  Email address
                  <input
                    type="email"
                    required
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <label>
                  <span style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>Password</span>
                    <button
                      type="button"
                      className="text-link"
                      style={{ border: 0, background: "none", padding: 0, fontSize: "10px" }}
                      onClick={() => switchMode("forgot")}
                    >
                      Forgot password?
                    </button>
                  </span>
                  <div className="password-input">
                    <input
                      type={show ? "text" : "password"}
                      required
                      autoComplete="current-password"
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
                <Notice>{error}</Notice>
                {info && <Notice type="success">{info}</Notice>}
                <Button loading={loading} type="submit" className="full-button">
                  Sign in <span>→</span>
                </Button>
              </form>
              <p>
                New here?{" "}
                <button
                  type="button"
                  className="text-link"
                  style={{ border: 0, background: "none", padding: 0 }}
                  onClick={() => switchMode("register")}
                >
                  Create a free studio account
                </button>
              </p>
            </>
          )}

          {mode === "register" && (
            <>
              <div className="eyebrow">GET STARTED</div>
              <h2>Create your studio account</h2>
              <p className="muted">Set your name and password to start creating AI Shorts.</p>
              <form onSubmit={submitRegister}>
                <label>
                  Full name
                  <input
                    type="text"
                    required
                    minLength={2}
                    autoComplete="name"
                    placeholder="e.g. Ali Raza"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label>
                  Email address
                  <input
                    type="email"
                    required
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <label>
                  Password (min 6 characters)
                  <div className="password-input">
                    <input
                      type={show ? "text" : "password"}
                      required
                      minLength={6}
                      autoComplete="new-password"
                      placeholder="Choose a password"
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
                <Notice>{error}</Notice>
                {info && <Notice type="success">{info}</Notice>}
                <Button loading={loading} type="submit" className="full-button">
                  Create account &amp; enter studio <span>→</span>
                </Button>
              </form>
              <p>
                Already registered?{" "}
                <button
                  type="button"
                  className="text-link"
                  style={{ border: 0, background: "none", padding: 0 }}
                  onClick={() => switchMode("login")}
                >
                  Sign in instead
                </button>
              </p>
            </>
          )}

          {mode === "forgot" && (
            <>
              <div className="eyebrow">ACCOUNT RECOVERY</div>
              <h2>Reset your password</h2>
              <p className="muted">
                Enter your account email and we will send a 6-digit verification code.
              </p>
              <form onSubmit={submitForgot}>
                <label>
                  Email address
                  <input
                    type="email"
                    required
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                  />
                </label>
                <Notice>{error}</Notice>
                <Button loading={loading} type="submit" className="full-button">
                  Send verification code <span>→</span>
                </Button>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px" }}>
                  <button
                    type="button"
                    className="text-link"
                    style={{ border: 0, background: "none", padding: 0 }}
                    onClick={() => switchMode("login")}
                  >
                    <ArrowLeft size={12} /> Back to sign in
                  </button>
                  <button
                    type="button"
                    className="text-link"
                    style={{ border: 0, background: "none", padding: 0 }}
                    onClick={() => switchMode("reset")}
                  >
                    Already have a code?
                  </button>
                </div>
              </form>
            </>
          )}

          {mode === "reset" && (
            <>
              <div className="eyebrow">VERIFY &amp; RESET</div>
              <h2>Choose a new password</h2>
              <p className="muted">
                Enter the 6-digit verification code and your new password (at least 10 characters).
              </p>
              <form onSubmit={submitReset}>
                {info && <Notice type="info">{info}</Notice>}
                <label>
                  Email address
                  <input
                    type="email"
                    required
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <label>
                  6-digit verification code
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="\d{6}"
                    maxLength={6}
                    required
                    autoComplete="one-time-code"
                    placeholder="123456"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  />
                </label>
                <label>
                  New password <span className="label-hint">(min. 10 characters)</span>
                  <div className="password-input">
                    <input
                      type={show ? "text" : "password"}
                      required
                      minLength={10}
                      maxLength={128}
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
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
                  Confirm new password
                  <input
                    type={show ? "text" : "password"}
                    required
                    minLength={10}
                    maxLength={128}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </label>
                <Notice>{error}</Notice>
                <Button loading={loading} type="submit" className="full-button">
                  Reset password &amp; sign in <span>→</span>
                </Button>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px" }}>
                  <button
                    type="button"
                    className="text-link"
                    style={{ border: 0, background: "none", padding: 0 }}
                    onClick={() => switchMode("forgot")}
                  >
                    Resend code
                  </button>
                  <button
                    type="button"
                    className="text-link"
                    style={{ border: 0, background: "none", padding: 0 }}
                    onClick={() => switchMode("login")}
                  >
                    <ArrowLeft size={12} /> Back to sign in
                  </button>
                </div>
              </form>
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
