import ChannelDefaults from "../components/ChannelDefaults";
import { useEffect, useState } from "react";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";
import { api } from "../services/api";

const GEMINI_MODEL_OPTIONS = [
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash (Recommended Primary)" },
  { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite (Higher Free Limit)" },
  { value: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite" },
  { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
  { value: "gemini-flash-latest", label: "Gemini Flash Latest" },
  { value: "gemma-3-27b-it", label: "Gemma 3 27B (14,400 req/day Free Tier)" },
  { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash (20 req/day Free Limit)" },
];

export default function Settings() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [aiForm, setAiForm] = useState({
    gemini_model: "gemini-2.5-flash",
    gemini_fallback_model: "gemini-2.5-flash-lite",
    gemini_fallback_models: "gemini-2.5-flash-lite,gemini-3.5-flash-lite,gemini-2.0-flash,gemini-flash-latest,gemma-3-27b-it",
    gemini_api_key: "",
    gemini_api_keys: "",
    groq_api_key: "",
    groq_model: "llama-3.3-70b-versatile",
    openai_compat_base_url: "",
    openai_compat_api_key: "",
    openai_compat_model: "",
    ollama_base_url: "http://127.0.0.1:11434",
    ollama_model: "",
    ai_auto_detect_ollama: true,
    title_short_ai_model: "",
  });
  const [aiTests, setAiTests] = useState(null);
  const [music, setMusic] = useState([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const owner = localStorage.getItem("role") === "OWNER";

  async function loadAll() {
    const [settingsData, tracks] = await Promise.all([api("/settings"), api("/music")]);
    setData(settingsData);
    setForm(settingsData.preferences);
    setMusic(tracks);
    const st = settingsData.active_configuration?.ai_status;
    if (st) {
      setAiForm((prev) => ({
        ...prev,
        gemini_model: st.gemini_primary_model || prev.gemini_model,
        gemini_fallback_models: (st.gemini_cascade_models || []).slice(1).join(",") || prev.gemini_fallback_models,
        groq_model: st.groq_model || prev.groq_model,
        openai_compat_base_url: st.openai_compat_base_url || "",
        openai_compat_model: st.openai_compat_model || "",
        ollama_base_url: st.ollama_base_url || "http://127.0.0.1:11434",
        ollama_model: "",
      }));
    }
  }

  useEffect(() => {
    let live = true;
    loadAll().catch((err) => { if (live) setError(err.message); });
    return () => { live = false; };
  }, []);

  const change = (key, value) => setForm((old) => ({ ...old, [key]: value }));

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const result = await api("/settings", { method: "PUT", body: JSON.stringify(form) });
      setForm(result.preferences);
      setSaved("Settings saved. New generation jobs use these preferences.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveAiProviders(event) {
    event.preventDefault();
    setAiBusy(true);
    setError("");
    setSaved("");
    try {
      await api("/settings/ai-providers", { method: "PUT", body: JSON.stringify(aiForm) });
      setAiForm((prev) => ({
        ...prev,
        gemini_api_key: "",
        gemini_api_keys: "",
        groq_api_key: "",
        openai_compat_api_key: "",
      }));
      await loadAll();
      setSaved("AI providers and cascade updated immediately (no server restart needed).");
    } catch (err) {
      setError(err.message);
    } finally {
      setAiBusy(false);
    }
  }

  async function runAiTest() {
    setAiBusy(true);
    setError("");
    try {
      const res = await api("/settings/ai-test", { method: "POST" });
      setAiTests(res.checks || []);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setAiBusy(false);
    }
  }

  async function uploadMusic(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const body = new FormData(event.currentTarget);
      await api("/music", { method: "POST", body });
      setMusic(await api("/music"));
      setSaved("Licensed music track added.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!form) return error ? <Notice>{error}</Notice> : <Loading />;
  const aiStat = data.active_configuration?.ai_status || {};

  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE PREFERENCES"
        title="Settings & AI Quota Relief"
        description="Configure multi-model AI cascades, backup free providers (Groq / OpenRouter / Ollama), and generation defaults."
      />
      <Notice>{error}</Notice>
      <Notice type="info">{saved}</Notice>

      {owner && (
        <section className="studio-card" style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap", marginBottom: 14 }}>
            <div>
              <h2 style={{ margin: "0 0 4px" }}>AI Providers &amp; Quota Relief Cascade</h2>
              <p className="vault-helper-text" style={{ margin: 0 }}>
                Automatically switches models &amp; keys if any free Gemini model hits its limit (e.g. 20 req/day on 3.8-flash), then falls back to Groq or local Ollama.
              </p>
            </div>
            <Button type="button" variant="secondary" loading={aiBusy} onClick={runAiTest}>
              Test Active AI Providers
            </Button>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            <span className={`status-pill ${aiStat.gemini_configured ? "status-active" : "status-inactive"}`}>
              Gemini Keys: {aiStat.gemini_key_count || 0} {aiStat.gemini_key_hints?.length ? `(${aiStat.gemini_key_hints.join(", ")})` : ""}
            </span>
            <span className={`status-pill ${aiStat.groq_configured ? "status-active" : "status-inactive"}`}>
              Groq Backup: {aiStat.groq_configured ? aiStat.groq_model : "Not set"}
            </span>
            <span className={`status-pill ${aiStat.ollama_detected_model || aiStat.ollama_configured ? "status-active" : "status-inactive"}`}>
              Local Ollama: {aiStat.ollama_detected_model || (aiStat.ollama_configured ? "Configured" : "Not detected")}
            </span>
            {aiStat.last_success?.model && (
              <span className="status-pill status-active">
                Last OK: {aiStat.last_success.provider}/{aiStat.last_success.model} ({aiStat.last_success.at})
              </span>
            )}
          </div>

          {!!aiStat.active_cooldowns?.length && (
            <div className="notice" style={{ marginBottom: 16 }}>
              <strong>Rate-limited models currently in cooldown (auto-skipped):</strong>{" "}
              {aiStat.active_cooldowns.map((c) => `${c.slot} (${Math.ceil(c.remaining_seconds / 60)}m left)`).join(" · ")}
            </div>
          )}

          {aiTests && (
            <div className="studio-card" style={{ marginBottom: 16, padding: 14, background: "#f8fafc" }}>
              <strong style={{ display: "block", marginBottom: 8 }}>Live Provider Diagnostics</strong>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {aiTests.map((t, idx) => (
                  <span key={idx} className={`status-pill ${t.status === "ok" ? "status-active" : "status-inactive"}`}>
                    {t.provider} · {t.model} ({t.key}): <b>{t.status}</b>
                  </span>
                ))}
              </div>
            </div>
          )}

          <form onSubmit={saveAiProviders}>
            <div className="studio-controls-grid">
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-primary-model">Primary Gemini Model</label>
                <select
                  id="ai-primary-model"
                  value={aiForm.gemini_model}
                  onChange={(e) => setAiForm({ ...aiForm, gemini_model: e.target.value })}
                >
                  {GEMINI_MODEL_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-fallback-models">Automatic Gemini Cascade Order</label>
                <input
                  id="ai-fallback-models"
                  value={aiForm.gemini_fallback_models}
                  onChange={(e) => setAiForm({ ...aiForm, gemini_fallback_models: e.target.value })}
                  placeholder="gemini-2.5-flash-lite,gemini-3.5-flash-lite,gemini-2.0-flash,gemma-3-27b-it"
                />
              </div>
            </div>

            <div className="studio-controls-grid">
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-extra-keys">Additional Gemini API Keys (comma or line separated — optional)</label>
                <textarea
                  id="ai-extra-keys"
                  rows={2}
                  value={aiForm.gemini_api_keys}
                  onChange={(e) => setAiForm({ ...aiForm, gemini_api_keys: e.target.value })}
                  placeholder="Leave blank to keep existing keys, or paste extra free AI Studio keys here"
                />
              </div>
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-groq-key">Free Groq API Key (Optional Backup — ~1,000+ req/day free)</label>
                <input
                  id="ai-groq-key"
                  type="password"
                  value={aiForm.groq_api_key}
                  onChange={(e) => setAiForm({ ...aiForm, groq_api_key: e.target.value })}
                  placeholder={aiStat.groq_configured ? "Configured (leave blank to keep)" : "gsk_... from console.groq.com"}
                />
                <span className="vault-helper-text">Model: {aiForm.groq_model} — automatically triggers when all Gemini models hit 429.</span>
              </div>
            </div>

            <div className="studio-controls-grid">
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-compat-url">OpenAI-Compatible Base URL (OpenRouter / Cerebras / LM Studio)</label>
                <input
                  id="ai-compat-url"
                  value={aiForm.openai_compat_base_url}
                  onChange={(e) => setAiForm({ ...aiForm, openai_compat_base_url: e.target.value })}
                  placeholder="e.g. https://openrouter.ai/api/v1"
                />
              </div>
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-compat-model">Model Name</label>
                <input
                  id="ai-compat-model"
                  value={aiForm.openai_compat_model}
                  onChange={(e) => setAiForm({ ...aiForm, openai_compat_model: e.target.value })}
                  placeholder="e.g. meta-llama/llama-3.3-70b-instruct:free"
                />
              </div>
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-compat-key">API Key (Optional)</label>
                <input
                  id="ai-compat-key"
                  type="password"
                  value={aiForm.openai_compat_api_key}
                  onChange={(e) => setAiForm({ ...aiForm, openai_compat_api_key: e.target.value })}
                  placeholder="Leave blank to keep existing"
                />
              </div>
            </div>

            <div className="studio-controls-grid">
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-ollama-url">Local Ollama URL (Unlimited 0 Quota)</label>
                <input
                  id="ai-ollama-url"
                  value={aiForm.ollama_base_url}
                  onChange={(e) => setAiForm({ ...aiForm, ollama_base_url: e.target.value })}
                />
              </div>
              <div className="studio-field">
                <label className="studio-label" htmlFor="ai-ollama-model">Ollama Model (blank = auto-detect)</label>
                <input
                  id="ai-ollama-model"
                  value={aiForm.ollama_model}
                  onChange={(e) => setAiForm({ ...aiForm, ollama_model: e.target.value })}
                  placeholder={aiStat.ollama_detected_model || "e.g. llama3.1:8b or qwen2.5:7b"}
                />
              </div>
            </div>

            <Button type="submit" loading={aiBusy}>
              Save AI Providers &amp; Clear Cooldowns
            </Button>
          </form>
        </section>
      )}

      {owner && <ChannelDefaults />}
      <div className="settings-grid">
        <section className="panel settings-section">
          <h2>AI &amp; YouTube connections</h2>
          {Object.entries(data.providers).map(([name, configured]) => (
            <p key={name}>
              <strong>{name.replaceAll("_", " ")}</strong>
              <span className={`status-pill ${configured ? "status-active" : "status-inactive"}`}>
                {configured ? "Configured" : "Not configured"}
              </span>
            </p>
          ))}
          <p>Publishing worker: {data.uploads_enabled ? "Enabled" : "Disabled by server configuration"}</p>
          <p className="muted">Secret values remain strictly on the backend.</p>
          <p>{data.thumbnail_note}</p>
          <a href={data.thumbnail_help} target="_blank" rel="noreferrer">Official Shorts thumbnail guidance ↗</a>
        </section>

        <form className="panel settings-section form-stack" onSubmit={save}>
          <h2>Generation defaults</h2>
          <fieldset disabled={!owner || busy}>
            <h3>Voice</h3>
            <div className="form-row">
              <div className="studio-field">
                <label className="studio-label">Provider</label>
                <select value={form.default_provider} onChange={(e) => change("default_provider", e.target.value)}>
                  <option value="auto">Auto / compatible narrator</option>
                  <option value="local">Local / free</option>
                  <option value="google">Google Cloud</option>
                  <option value="elevenlabs">ElevenLabs</option>
                </select>
              </div>
              <div className="studio-field">
                <label className="studio-label">Generic narrator voice</label>
                <input value={form.default_voice} onChange={(e) => change("default_voice", e.target.value)} />
              </div>
            </div>
            <div className="studio-field">
              <label className="studio-label">Voice speed</label>
              <input type="number" min="0.75" max="1.4" step="0.05" value={form.voice_speed} onChange={(e) => change("voice_speed", Number(e.target.value))} />
            </div>
            <h3>Video &amp; captions</h3>
            <div className="form-row">
              <div className="studio-field">
                <label className="studio-label">Default duration</label>
                <select value={form.default_duration} onChange={(e) => change("default_duration", Number(e.target.value))}>
                  {[30, 45, 60].map((v) => <option key={v} value={v}>{v} seconds</option>)}
                </select>
              </div>
              <div className="studio-field">
                <label className="studio-label">Subtitle preset</label>
                <select value={form.subtitle_mode} onChange={(e) => change("subtitle_mode", e.target.value)}>
                  <option value="sentence">Sentence</option>
                  <option value="word-highlight">Word highlight</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="studio-field">
                <label className="studio-label">Font size</label>
                <input type="number" min="36" max="90" value={form.font_size} onChange={(e) => change("font_size", Number(e.target.value))} />
              </div>
              <div className="studio-field">
                <label className="studio-label">Max words per caption</label>
                <input type="number" min="2" max="9" value={form.max_words} onChange={(e) => change("max_words", Number(e.target.value))} />
              </div>
            </div>
            <div className="form-row">
              <div className="studio-field">
                <label className="studio-label">Position</label>
                <select value={form.caption_position} onChange={(e) => change("caption_position", e.target.value)}>
                  <option value="bottom">Lower safe area</option>
                  <option value="center">Center</option>
                </select>
              </div>
              <div className="studio-field">
                <label className="studio-label">Highlight color</label>
                <input type="color" value={form.highlight_color} onChange={(e) => change("highlight_color", e.target.value)} />
              </div>
            </div>
            <label className="studio-checkbox-row">
              <input type="checkbox" checked={form.transitions} onChange={(e) => change("transitions", e.target.checked)} />
              <span>Crossfades and subtle motion</span>
            </label>
            <div className="studio-field">
              <label className="studio-label">Background music</label>
              <select value={form.background_music_id || ""} onChange={(e) => change("background_music_id", e.target.value || null)}>
                <option value="">No music</option>
                {music.map((track) => <option value={track.id} key={track.id}>{track.name}</option>)}
              </select>
            </div>
            <h3>Research</h3>
            <div className="studio-field">
              <label className="studio-label">Provider</label>
              <select value={form.research_provider} onChange={(e) => change("research_provider", e.target.value)}>
                <option value="demo">Local demo (not publishable)</option>
                <option value="rss">Real RSS sources</option>
              </select>
            </div>
            {owner && <Button loading={busy} type="submit">Save settings</Button>}
          </fieldset>
          {!owner && <p>Only workspace owners can change settings.</p>}
        </form>
      </div>

      {owner && (
        <section className="panel settings-section">
          <h2>Add licensed background music</h2>
          <form className="form-stack" onSubmit={uploadMusic}>
            <div className="studio-field">
              <label className="studio-label">Audio file</label>
              <input required type="file" name="file" accept=".mp3,.wav,.m4a,.ogg" />
            </div>
            <div className="form-row">
              <div className="studio-field">
                <label className="studio-label">Source / URL</label>
                <input required name="source" maxLength={1000} />
              </div>
              <div className="studio-field">
                <label className="studio-label">License / usage rights</label>
                <input required name="license" maxLength={500} />
              </div>
            </div>
            <div className="studio-field">
              <label className="studio-label">Attribution</label>
              <input required name="attribution" maxLength={500} />
            </div>
            <Button loading={busy} type="submit" variant="secondary">Add music track</Button>
          </form>
        </section>
      )}
    </>
  );
}
