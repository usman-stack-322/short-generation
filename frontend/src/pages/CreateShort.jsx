import PersonalityPicker from "../components/PersonalityPicker";
import LanguageSelect from "../components/LanguageSelect";
import VoiceStyleSelect from "../components/VoiceStyleSelect";
import ResearchPicker from "../components/ResearchPicker";
import { useEffect, useState } from "react";
import { ArrowRight, Check, Clapperboard, Clock3, FileText, Image, Mic2, Sparkles, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Notice, Loading } from "../components/UI";

export default function CreateShort() {
  const [providerStatus, setProviderStatus] = useState(null);
  const [initialized, setInitialized] = useState(false);
  const [channels, setChannels] = useState([]);
  const [personalities, setPersonalities] = useState([]);
  const [collections,setCollections]=useState([]);
  const [form, setForm] = useState({
    channel_id: "",
    personality_id: "",
    topic_mode: "current",
    manual_topic: "",
    duration: 45,
    voice: "",
    voice_style: "auto",
    tts_provider: "auto",
    language: "en-US",
    video_style: "Documentary",
    candidate_id: null,
    content_mode: 'hybrid',collection_id:null,avoid_recent_media:true,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api('/library/collections').then(setCollections).catch(err=>setError(err.message));
    Promise.all([api("/channels"), api("/personalities"), api("/settings")])
      .then(([channelRows, personalityRows, settings]) => {
        setProviderStatus(settings.active_configuration);
        setChannels(channelRows);
        setPersonalities(personalityRows.filter((personality) => personality.enabled));
        setForm((previous) => ({
          ...previous,
          channel_id: channelRows[0]?.id || "",
          duration: channelRows[0]?.generation_duration || 45,
          video_style: channelRows[0]?.operational_defaults?.template || "Documentary",
          voice_style: channelRows[0]?.voice_style || "auto",
          language: channelRows[0]?.default_language || "en-US",
          personality_id: personalityRows.find((personality) => personality.enabled && (!personality.channel_id || personality.channel_id === channelRows[0]?.id))?.id || "",
        }));
      })
      .catch((err) => setError(err.message)).finally(() => setInitialized(true));
  }, []);

  const eligiblePersonalities = personalities.filter(p => !p.channel_id || p.channel_id === form.channel_id);
  const selectedPersonality = personalities.find((personality) => personality.id === form.personality_id);
  const change = (key, value) => setForm((current) => {
    const next = { ...current, [key]: value };
    if (["channel_id","personality_id","topic_mode"].includes(key)) next.candidate_id = null;
    if (key === "channel_id") { const channel = channels.find(c => c.id === value); next.voice_style = channel?.voice_style || "auto"; next.voice = ""; next.tts_provider = "auto"; next.language = channel?.default_language || "en-US"; next.duration=channel?.generation_duration||45; next.video_style=channel?.operational_defaults?.template||"Documentary"; }
    if (key === 'channel_id') next.collection_id=null;
    if (key === "channel_id") next.personality_id = personalities.find(p => !p.channel_id || p.channel_id === value)?.id || "";
    if (key === "personality_id") { const p = personalities.find(p => p.id === value); if (p) { next.duration = p.default_duration; next.voice_style = p.default_voice_style || "auto";  next.voice = ""; } }
    if (key === "language") next.voice = "";
    return next;
  });

  async function generate(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const payload={ ...form, voice: form.voice || null, tts_provider: form.tts_provider || null, duration: Number(form.duration) };
      // Retain intent across network failures/reloads, but a successful submit
      // followed by a new form is an explicit new generation operation.
      const userId=JSON.parse(localStorage.getItem('user') || '{}')?.id || 'local';
      const operationKey=`short-operation:${userId}:${JSON.stringify(payload)}`;
      const operationId=sessionStorage.getItem(operationKey) || crypto.randomUUID();
      sessionStorage.setItem(operationKey,operationId);
      const job = await api("/videos/generate", {
        method: "POST",
        body: JSON.stringify({...payload,operation_id:operationId}),
      });
      sessionStorage.removeItem(operationKey);
      navigate(`/videos/${job.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (!initialized) return <Loading />;
  if (!channels.length) return <><PageHeader title="Create a Short" description="Choose a channel before starting your first story."/><Notice>{error}</Notice><section className="panel review-detail"><h2>No channels available</h2><p>Add a channel in Channels, or ask your workspace owner to assign you one.</p></section></>;
  return (
    <>
      <PageHeader
        eyebrow="THE SHORT-FORM WORKFLOW"
        title="Create a Short"
        description="Turn a story idea into a ready-to-review vertical video."
      />
      <div className="create-layout">
        <form className="create-form panel" onSubmit={generate}>
          <div className="form-section"><h2>Content mode</h2><label>Workflow<select value={form.content_mode} onChange={e=>change('content_mode',e.target.value)}><option value="hybrid">Hybrid (recommended)</option><option value="auto">Auto Research</option><option value="my_assets">My Assets</option></select></label><p>Every mode retains factual verification. My Assets uses saved photos and clearly labeled text cards, with no online photo search.</p>{form.content_mode!=='auto'&&<><label>Approved media collection<select required={form.content_mode==='my_assets'} value={form.collection_id||''} onChange={e=>change('collection_id',e.target.value||null)}><option value="">Automatic: matching assigned collection, then online</option>{collections.filter(c=>c.channel_id===form.channel_id).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label><input type="checkbox" checked={form.avoid_recent_media} onChange={e=>change('avoid_recent_media',e.target.checked)}/> Prefer least recently used photos</label></>}</div>
          <div className="form-section"><div className="section-title"><span className="step-number">01</span><h2>Channel</h2></div>
            <label>Channel<select required value={form.channel_id} onChange={e=>change('channel_id',e.target.value)}><option value="">Choose a channel</option>{channels.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          </div>
          <div className="form-section"><div className="section-title"><span className="step-number">02</span><h2>Personality</h2></div>
            <PersonalityPicker rows={eligiblePersonalities} value={form.personality_id} channelId={form.channel_id} language={form.language}
              onChange={value=>change('personality_id',value)} onCreated={(rows,id)=>{setPersonalities(rows.filter(row=>row.enabled));const row=rows.find(row=>row.id===id);setForm(current=>({...current,personality_id:id,candidate_id:null,language:row.preferred_language,voice_style:row.default_voice_style||'auto'}));}}/>
            {selectedPersonality&&<small>{selectedPersonality.category} / {selectedPersonality.tone}</small>}
          </div>
          <div className="form-section"><div className="section-title"><span className="step-number">03</span><h2>Topic source</h2></div>
            <div className="topic-mode"><button type="button" className={form.topic_mode==='current'?'selected':''} onClick={()=>change('topic_mode','current')}><Sparkles size={16}/><span><strong>Current Topic</strong><small>{providerStatus?.research_provider==='rss'?'Live RSS sources':'Development research (not live)'}</small></span></button>
            <button type="button" className={form.topic_mode==='manual'?'selected':''} onClick={()=>change('topic_mode','manual')}><FileText size={16}/><span><strong>Manual Topic</strong><small>Your own story idea</small></span></button></div>
            {form.topic_mode==='manual'&&<label>Topic<input required maxLength={300} value={form.manual_topic} onChange={e=>change('manual_topic',e.target.value)}/></label>}
              {form.topic_mode==='current' && channels.find(c=>c.id===form.channel_id)?.automatic_evergreen_fallback && <small>Automatic fallback enabled: verified news first, then independently verified historical stories. Limited-verification drafts still require an explicit action.</small>}
              {form.topic_mode==='current'&&<ResearchPicker key={`${form.channel_id}:${form.personality_id}`} channelId={form.channel_id} personalityId={form.personality_id} selected={form.candidate_id} onSelect={value=>change('candidate_id',value)} provider={providerStatus?.research_provider}/>}
          </div>
          <div className="form-section"><div className="section-title"><span className="step-number">04</span><h2>Language</h2></div><LanguageSelect value={form.language} onChange={value=>change('language',value)}/></div>
          <div className="form-section"><div className="section-title"><span className="step-number">05</span><h2>Voice</h2></div>
            <div className="form-row"><label>Voice Provider<select value={form.tts_provider} onChange={e=>change('tts_provider',e.target.value)}><option value="auto">Auto (compatible narrator)</option><option value="">Channel default</option><option value="local">Local</option><option value="google">Google</option><option value="elevenlabs">ElevenLabs</option></select></label><VoiceStyleSelect value={form.voice_style} onChange={value=>change('voice_style',value)}/></div>
            <label>Narrator (optional)<input value={form.voice} onChange={e=>change('voice',e.target.value)} placeholder="Automatic compatible narrator"/></label>
          </div>
          <div className="form-section"><div className="section-title"><span className="step-number">06</span><h2>Duration</h2></div><div className="form-row">
            <label>Video length<select value={form.duration} onChange={e=>change('duration',e.target.value)}><option value="30">30 seconds</option><option value="45">45 seconds</option><option value="60">60 seconds</option></select></label>
            <label>Video style<select value={form.video_style} onChange={e=>change('video_style',e.target.value)}><option>Documentary</option><option>News brief</option><option>Energetic</option><option>Explainer</option></select></label></div>
          </div>
          <div className="form-section"><div className="section-title"><span className="step-number">07</span><h2>Generate</h2></div><Notice>{error}</Notice>
            <Button type="submit" loading={loading} disabled={!form.channel_id || !form.personality_id} className="generate-button"><Zap size={16}/>{loading?'Creating your Short...':'Generate Short'}<ArrowRight size={16}/></Button>
            <small>Every video requires approval before publishing.</small>
          </div>
        </form>

        <aside className="create-aside">
          <div className="preview-card">
            <div className="preview-card-top"><span><Clapperboard size={15} /> VIDEO PREVIEW</span><span className="preview-vertical">9:16</span></div>
            <div className="video-mock">
              <div className="mock-glow" />
              <span className="mock-tag">YOUR NEXT STORY</span>
              <strong>{selectedPersonality?.name || "Your personality"}<br /><em>in {form.duration} seconds.</em></strong>
              <div className="mock-caption">Your script and narration will bring this scene to life.</div>
              <div className="mock-progress"><i /></div>
            </div>
            <div className="preview-info"><span><Clock3 size={14} />{form.duration} seconds</span><span><Mic2 size={14} />{form.voice}</span></div>
          </div>
          <div className="workflow-card">
            <h3>What happens next</h3>
            {[
              [Sparkles, "Research", "Find a topic and source"],
              [FileText, "Write", "Generate an original script"],
              [Mic2, "Narrate", "Create local voiceover"],
              [Image, "Produce", "Render vertical video + cover"],
            ].map(([Icon, title, text], index) => (
              <div className="workflow-row" key={title}>
                <span className={`workflow-icon workflow-${index}`}><Icon size={15} /></span>
                <span><strong>{title}</strong><small>{text}</small></span>
                {index < 3 && <span className="workflow-line" />}
              </div>
            ))}
            <div className="workflow-free"><Check size={13} /> Local-first · No upload until approval</div>
          </div>
          <div className="aside-footnote">Local demo assets are original generated graphics, not scraped images. A compatible narrator is required for your selected language.</div>
        </aside>
      </div>
      {result && (
        <div className="result-banner">
          <div className="success-icon"><Check size={20} /></div>
          <div><strong>Your Short is ready for review</strong><p>{result.seo?.title || result.topic}</p></div>
          <Button variant="secondary" onClick={() => navigate(`/videos/${result.id}`)}>Review video <ArrowRight size={15} /></Button>
        </div>
      )}
    </>
  );
}
