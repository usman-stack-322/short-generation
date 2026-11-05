import AppearanceSelector from "../components/AppearanceSelector";
import BrandLogo from "../components/BrandLogo";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, LockKeyhole } from "lucide-react";
import { api } from "../services/api";
import { Button, Notice } from "../components/UI";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);
  const navigate = useNavigate();
  async function submit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      onLogin(result);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }
  return <div className="login-page"><div className="login-appearance"><AppearanceSelector /></div><div className="login-visual"><div className="login-brand"><BrandLogo /></div><div className="visual-copy"><span className="pill light-pill">THE SHORT-FORM STUDIO</span><h1>From big ideas<br />to <em>short stories.</em></h1><p>Research, write, and produce your next great Short — all in one creative workspace.</p><div className="visual-preview"><div className="preview-screen"><div className="preview-stars">✦ &nbsp; ✧ &nbsp; ✦</div><span>YOUR NEXT SHORT</span><strong>starts here.</strong><div className="preview-controls"><i /><i /><i /></div></div><div className="preview-note"><span className="live-dot" /> Creative momentum, in one place</div></div></div><div className="login-footer">A little more story in every scroll.</div></div><div className="login-panel"><div className="login-form-wrap"><span className="mobile-brand"><BrandLogo /></span><div className="login-icon"><LockKeyhole size={21} /></div><div className="eyebrow">WELCOME BACK</div><h2>Sign in to your studio</h2><p className="muted">Your next story is only a few clicks away.</p><form onSubmit={submit}><label>Email address<input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>Password<div className="password-input"><input type={show ? "text" : "password"} required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /><button type="button" aria-label="Toggle password" onClick={() => setShow(!show)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label><Notice>{error}</Notice><Button loading={loading} type="submit" className="full-button">Sign in <span>→</span></Button></form><p>Sign in with the account supplied by your platform administrator.</p><div className="secure-note"> <LockKeyhole size={13} /> Your workspace is private and secure</div></div><div className="login-legal">© 2026 AI Shorts <span>Built for creators, with care.</span></div></div></div>;
}
