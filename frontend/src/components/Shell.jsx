import AppearanceSelector from "./AppearanceSelector";
import BrandLogo from "./BrandLogo";
import { api, resetMediaSession } from "../services/api";
import Notifications from "./Notifications";
import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Bell, ChevronDown, Clapperboard, Download, LayoutDashboard, LogOut,
  Menu, Settings, Sparkles, Users, WandSparkles,
} from "lucide-react";

const links = [
  ["/", "Dashboard", LayoutDashboard, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/title-to-short", "Create Short", WandSparkles, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/celebrity-library", "Celebrity Folder", Clapperboard, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/videos", "My Videos", Clapperboard, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/review-queue", "Review Queue", Sparkles, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/uploads", "Export History", Download, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/library", "Media Library", Clapperboard, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/team", "Team & Roles", Users, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
  ["/account", "Account Settings", Settings, ["OWNER", "ADMIN", "MEMBER", "EDITOR", "VIEWER"]],
];

function roleLabel(role) {
  if (role === "OWNER") return "Owner";
  if (role === "ADMIN") return "Admin";
  if (role === "MEMBER" || role === "EDITOR") return "Employee";
  return role || "Employee";
}

export function Shell({ user, children }) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [configuration, setConfiguration] = useState(null);
  const [workspace,setWorkspace] = useState(null);
  const [workspaces,setWorkspaces] = useState([]);
  useEffect(() => {
    api('/workspaces').then(setWorkspaces).catch(() => {});
  }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const close = event => { if (event.key === 'Escape') setMenuOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [menuOpen]);
  useEffect(() => {
    let live = true;
    const load = () => api('/settings').then(data => { if (live) {setConfiguration(data.active_configuration);setWorkspace(data.workspace);} }).catch(() => { if (live) setConfiguration(null); });
    load();
    window.addEventListener('focus', load);
    const timer = setInterval(load, 30000);
    return () => { live = false; clearInterval(timer); window.removeEventListener('focus', load); };
  }, []);
  const providerLabel = !configuration ? 'Provider status unavailable' :
    (configuration.ai_configured || configuration.gemini_configured) ? (configuration.research_provider === 'rss' ? 'Smart AI Cascade + RSS' : 'Smart AI Cascade') :
    configuration.research_provider === 'rss' ? 'Live RSS / AI not configured' : 'Development providers';
  const [role,setRole] = useState(localStorage.getItem("role") || "MEMBER");
  useEffect(()=>{let live=true;const refresh=()=>api('/auth/me').then(me=>{if(live){localStorage.setItem('role',me.role);setRole(me.role);}}).catch(()=>{});refresh();const timer=setInterval(refresh,10000);window.addEventListener('focus',refresh);return()=>{live=false;clearInterval(timer);window.removeEventListener('focus',refresh);};},[]);
  const logout = async () => {
    try { await api("/auth/logout",{method:"POST"}); } catch {}
    resetMediaSession();
    localStorage.removeItem("workspace_id");
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    localStorage.removeItem("role");
    navigate("/login");
  };
  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "mobile-open" : ""}`}>
        <div className="brand"><BrandLogo compact /></div>
        <div className="workspace-picker">
          <span className="workspace-logo">{workspace?.name?.slice(0,1).toUpperCase() || 'W'}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            {workspaces.length > 1 ? (
              <select
                aria-label="Workspace switcher"
                className="workspace-select-native"
                value={localStorage.getItem('workspace_id') || workspace?.id || ''}
                onChange={e => { localStorage.setItem('workspace_id', e.target.value); window.location.reload(); }}
              >
                {workspaces.map(w => (
                  <option key={w.workspace_id} value={w.workspace_id} style={{ color: '#111' }}>
                    {w.name} ({w.role})
                  </option>
                ))}
              </select>
            ) : (
              <div className="workspace-name">{workspace?.name || 'Owner workspace'}</div>
            )}
            <span className="role-badge-chip">{roleLabel(role)}</span>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">{links.filter(([, , , roles]) => roles.includes(role)).map(([to, label, Icon]) => <NavLink key={to} aria-label={label} title={label} to={to} onClick={() => setMenuOpen(false)} end={to === "/"} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon size={17} /><span>{label}</span></NavLink>)}</nav>
        <div className="sidebar-bottom">
          <div className="upgrade-card"><span className="upgrade-icon"><Sparkles size={16} /></span><strong>Make more with AI</strong><p>{!configuration ? 'Checking provider configuration.' : configuration.ai_configured || configuration.gemini_configured ? 'AI cascade is ready for Title-to-Short creation.' : 'Connect your AI provider or use Title-to-Short studio.'}</p><button onClick={() => navigate(["OWNER","ADMIN"].includes(role) ? "/settings" : "/title-to-short")}>{["OWNER","ADMIN"].includes(role) ? "Explore settings" : "Create a Short"} <span>↗</span></button></div>
          <div className="profile"><div className="avatar">{(user?.name || "U").slice(0, 1).toUpperCase()}</div><div className="profile-copy"><strong>{user?.name || "Studio User"}</strong><small>{roleLabel(role)}</small></div><button className="icon-button" title="Sign out" onClick={logout}><LogOut size={16} /></button></div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar"><button className="mobile-menu icon-button" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><Menu size={18} /></button><div className="crumb">Workspace <span>/</span> <strong>Studio</strong></div><div className="topbar-actions"><button type="button" className="plan-chip" style={{cursor: ["OWNER","ADMIN"].includes(role) ? 'pointer' : 'default'}} onClick={() => ["OWNER","ADMIN"].includes(role) && navigate('/settings')} title="AI Provider & Quota Settings"><span className="status-dot" /> {providerLabel}</button><AppearanceSelector /><Notifications /><div className="small-avatar">{(user?.name || "D").slice(0, 1).toUpperCase()}</div><span className="topbar-user">{user?.name || "Demo Owner"}</span></div></header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, action }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

export function EmptyState({ title, detail, action }) {
  return <div className="empty-state"><div className="empty-icon"><Clapperboard size={22} /></div><strong>{title}</strong><p>{detail}</p>{action}</div>;
}

