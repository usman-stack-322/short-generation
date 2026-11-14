import { useEffect, useState, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, mediaUrl } from '../services/api';
import { PageHeader } from '../components/Shell';
import { Button } from '../components/UI';
import { Copy, FileText, Film, FolderOpen, Image as ImageIcon, Search, Trash2, Upload } from 'lucide-react';
import './TitleShort.css';

const active = new Set(['analyzing','researching','research_verification','script','validating','visuals','voiceover','rendering']);
const steps = [['analyzing','Topic check'],['researching','Web research'],['script','Script ready'],['visuals','Visuals'],['voiceover','Voiceover'],['rendering','Render']];

export default function TitleShort() {
  const { id } = useParams();
  const navigate = useNavigate();
  const request = useRef(null);
  const visualsRequested = useRef(new Set());
  const [form,setForm] = useState({
    title:'',duration:45,language:'English',style:'educational',
    media_mode:'online',media_preference:'mix_both',
    narrator:'automatic',voice:'',
    voice_style:'Newscaster',voice_pace:'Rapid',voice_accent:'American English',
    caption_style:'viral_gold',
  });
  const narratorTouched = useRef(false);
  const [collections,setCollections]=useState([]),[localMedia,setLocalMedia]=useState([]);
  const [reviewNotice,setReviewNotice]=useState('');
  useEffect(()=>{
    api('/library/collections').then(c=>setCollections(c)).catch(e=>setError(e.message));
  },[]);
  const [sourceText,setSourceText] = useState('');
  const [capabilities,setCapabilities] = useState(null);
  const [draft,setDraft] = useState(null);
  useEffect(()=>{if(draft?.collection_id)api('/library/collections/'+draft.collection_id+'/media?approved=true').then(setLocalMedia).catch(e=>setError(e.message));},[draft?.collection_id]);

  const [history,setHistory] = useState([]);
  const [texts,setTexts] = useState([]);
  const [instructions,setInstructions] = useState({});
  const [vaultLibrary,setVaultLibrary] = useState(null);
  const [vaultPickerScene,setVaultPickerScene] = useState(null);
  const [vaultSearch,setVaultSearch] = useState('');
  useEffect(()=>{api('/assets/library').then(setVaultLibrary).catch(()=>{});},[id]);
  const [dirty,setDirty] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  useEffect(()=>{
    api('/title-shorts/capabilities').then(caps=>{
      setCapabilities(caps);
      if(!narratorTouched.current && caps?.voices?.some(v=>v.provider==='gemini_tts')){
        setForm(f=>f.narrator==='automatic' ? {...f,narrator:'gemini_tts',voice:'Charon'} : f);
      }
    }).catch(e=>setError(e.message));
  },[]);
  useEffect(()=>{if(draft)setSourceText((draft.source_urls||[]).join('\n'));},[draft?.id]);
  useEffect(()=>{ let live=true; api('/title-shorts').then(rows=>{if(live)setHistory(rows);}).catch(e=>{if(live)setError(e.message);}); return()=>{live=false;}; },[id]);
  useEffect(()=>{
    let live=true, timer;
    setDraft(null);setTexts([]);setDirty(false);setError('');setInstructions({});
    if(!id)return;
    const load=async()=>{
      try {const row=await api('/title-shorts/'+id);if(!live)return;setDraft(row);}
      catch(e){if(live)setError(e.message);}
    };
    load();return()=>{live=false;clearTimeout(timer);};
  },[id]);
  // Polling updates never overwrite unsaved local narration edits.
  useEffect(()=>{if(draft&&!dirty)setTexts(draft.scenes.map(s=>s.narration));},[draft,dirty]);
  const running=busy||active.has(draft?.status);
  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    if (!running) { setElapsedSec(0); return; }
    setElapsedSec(0);
    const tick = setInterval(() => setElapsedSec(s => s + 1), 1000);
    return () => clearInterval(tick);
  }, [running, draft?.status]);

  async function action(path,body,method='POST') {
    setBusy(true);setError('');
    try {
      const row=await api('/title-shorts'+path,{method,body:JSON.stringify(body)});
      setDirty(false);setDraft(row);
      return row;
    } catch(e){setError(e.message);} finally{setBusy(false);}
  }

  useEffect(()=>{
    if(!draft||!active.has(draft.status))return;
    let live=true;
    const timer=setInterval(()=>api('/title-shorts/'+draft.id).then(row=>{if(live)setDraft(row);}).catch(e=>{if(live)setError(e.message);}),2000);
    return()=>{live=false;clearInterval(timer);};
  },[draft?.id,draft?.status]);

  // Automatically fetch online visuals for scenes in script_review when missing.
  useEffect(()=>{
    if(!draft||draft.status!=='script_review'||draft.media_mode==='local'||draft.error_message||busy)return;
    if(!draft.scenes?.some(s=>!s.preview_url))return;
    const key=draft.id+':'+draft.revision;
    if(visualsRequested.current.has(key))return;
    visualsRequested.current.add(key);
    action('/'+draft.id+'/visuals',{revision:draft.revision});
  },[draft?.id,draft?.status,draft?.revision,draft?.media_mode,draft?.error_message,busy]);

  async function uploadSceneMedia(sceneNumber, file, vaultAssetId='') {
    setBusy(true); setError('');
    try {
      const fd = new FormData();
      if (file) fd.append('file', file);
      if (vaultAssetId) fd.append('vault_asset_id', vaultAssetId);
      const row = await api('/projects/'+id+'/scenes/'+sceneNumber+'/upload-media', { method: 'POST', body: fd });
      setDirty(false); setDraft(row); setVaultPickerScene(null);
    } catch(e) { setError(e.message); } finally { setBusy(false); }
  }

  async function renderShort() {
    if (!draft) return;
    setBusy(true);
    setError('');
    setReviewNotice('');
    try {
      let current = draft;
      if (current.scope?.required && !current.scope_accepted) {
        current = await api('/title-shorts/' + id + '/scope/accept', {
          method: 'POST',
          body: JSON.stringify({ revision: current.revision }),
        });
        setDraft(current);
      }
      const rendered = await api('/title-shorts/' + id + '/render', {
        method: 'POST',
        body: JSON.stringify({ revision: current.revision }),
      });
      setDirty(false);
      setDraft(rendered);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function create(event){
    event.preventDefault();
    const payload={...form,source_urls:sourceText.split(/\n/).map(s=>s.trim()).filter(Boolean)};
    const fingerprint=JSON.stringify(payload);
    if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,id:crypto.randomUUID()};
    const row=await action('',{...payload,request_id:request.current.id});
    if(row)navigate('/title-to-short/'+row.id);
  }

  const rawStage=draft?.status==='failed'?draft.failed_step:draft?.status;
  const stage=rawStage==='research_verification'?'researching':['script_review','validating'].includes(rawStage)?'script':rawStage;
  const stageIndex=steps.findIndex(([key])=>key===stage);

  const updateVoiceSettings = (isDraft, patch) => {
    if (!isDraft) {
      narratorTouched.current = true;
      setForm(f => ({ ...f, ...patch }));
      return;
    }
    action('/'+id+'/narrator', {
      revision: draft.revision,
      narrator: patch.narrator ?? (draft.narrator || 'automatic'),
      voice: patch.voice !== undefined ? patch.voice : (draft.preferred_voice || ''),
      voice_style: patch.voice_style ?? (draft.voice_style || 'Newscaster'),
      voice_pace: patch.voice_pace ?? (draft.voice_pace || 'Rapid'),
      voice_accent: patch.voice_accent ?? (draft.voice_accent || 'American English'),
      caption_style: patch.caption_style ?? (draft.caption_style || 'viral_gold'),
    }, 'PUT');
  };

  const renderVoiceSelect = (isDraft) => {
    const curNarrator = isDraft ? (draft.narrator||'automatic') : (form.narrator||'automatic');
    const curLang = isDraft ? draft.language : form.language;
    const targetProvider = (curNarrator && curNarrator!=='automatic') ? curNarrator : (capabilities?.languages[curLang]?.provider||'kokoro_onnx');
    const matching = (capabilities?.voices||[]).filter(v=>v.provider===targetProvider && (!v.language || v.language===curLang));
    const curVoice = isDraft ? (draft.preferred_voice||'') : (form.voice||'');
    const curStyle = isDraft ? (draft.voice_style||'Newscaster') : (form.voice_style||'Newscaster');
    const curPace = isDraft ? (draft.voice_pace||'Rapid') : (form.voice_pace||'Rapid');
    const curAccent = isDraft ? (draft.voice_accent||'American English') : (form.voice_accent||'American English');
    const curCaption = isDraft ? (draft.caption_style||'viral_gold') : (form.caption_style||'viral_gold');
    const studio = capabilities?.studio_controls || {};
    const styles = studio.styles || ['Newscaster','Documentary','Storyteller','Sports Hype','Conversational','Dramatic','Calm & Serious'];
    const paces = studio.paces || ['Rapid','Fast','Normal','Measured'];
    const accents = studio.accents || ['American English','British English','Australian English','Canadian English','Indian English','Neutral'];
    const captionStyles = studio.caption_styles || [
      {id:'viral_gold',label:'Viral Gold Pop (Bold Highlight)'},
      {id:'cyan_pop',label:'Electric Cyan Pop'},
      {id:'clean_broadcast',label:'Newscaster Broadcast'},
      {id:'classic',label:'Classic Minimal'},
    ];
    const locked = isDraft ? (running||dirty) : false;

    return (
      <>
        {matching.length>0 && (
          <div className="studio-field">
            <label className="studio-label" htmlFor={isDraft?'draft-voice':'create-voice'}>
              {targetProvider==='gemini_tts' ? 'Google AI Studio Voice' : 'Voice Preset'}
            </label>
            <select
              id={isDraft?'draft-voice':'create-voice'}
              disabled={locked}
              value={curVoice}
              onChange={e => updateVoiceSettings(isDraft, {voice: e.target.value})}
            >
              <option value="">Default ({targetProvider==='gemini_tts'?'Charon':(capabilities?.languages[curLang]?.voice||'auto')})</option>
              {matching.map(v=><option key={v.provider+':'+v.voice} value={v.voice}>{v.label}</option>)}
            </select>
          </div>
        )}
        <div className="studio-field">
          <label className="studio-label" htmlFor={isDraft?'draft-caption-style':'create-caption-style'}>Caption Style</label>
          <select
            id={isDraft?'draft-caption-style':'create-caption-style'}
            disabled={locked}
            value={curCaption}
            onChange={e => updateVoiceSettings(isDraft, {caption_style: e.target.value})}
          >
            {captionStyles.map(cs=><option key={cs.id} value={cs.id}>{cs.label}</option>)}
          </select>
        </div>
        {targetProvider==='gemini_tts' && (
          <div className="studio-controls-grid" style={{gridColumn:'1 / -1'}}>
            <div className="studio-field">
              <label className="studio-label" htmlFor={isDraft?'draft-voice-style':'create-voice-style'}>Speaking Style</label>
              <select
                id={isDraft?'draft-voice-style':'create-voice-style'}
                disabled={locked}
                value={curStyle}
                onChange={e => updateVoiceSettings(isDraft, {voice_style: e.target.value})}
              >
                {styles.map(s=><option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="studio-field">
              <label className="studio-label" htmlFor={isDraft?'draft-voice-pace':'create-voice-pace'}>Pace</label>
              <select
                id={isDraft?'draft-voice-pace':'create-voice-pace'}
                disabled={locked}
                value={curPace}
                onChange={e => updateVoiceSettings(isDraft, {voice_pace: e.target.value})}
              >
                {paces.map(p=><option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="studio-field">
              <label className="studio-label" htmlFor={isDraft?'draft-voice-accent':'create-voice-accent'}>Accent</label>
              <select
                id={isDraft?'draft-voice-accent':'create-voice-accent'}
                disabled={locked}
                value={curAccent}
                onChange={e => updateVoiceSettings(isDraft, {voice_accent: e.target.value})}
              >
                {accents.map(a=><option key={a} value={a}>{a}</option>)}
              </select>
            </div>
          </div>
        )}
      </>
    );
  };

  const canDownload = Boolean(draft?.video_url);
  const canRemoveDraft = (row) => !!row && !active.has(row.status);

  async function removeDraft(targetId, title, navigateHome = false) {
    if (!window.confirm(`Remove draft "${title || 'this draft'}" permanently?`)) return;
    setBusy(true);
    setError('');
    setReviewNotice('');
    try {
      await api('/title-shorts/' + targetId, { method: 'DELETE' });
      const rows = await api('/title-shorts');
      setHistory(rows || []);
      if (navigateHome) {
        request.current = null;
        navigate('/title-to-short');
      } else {
        setReviewNotice(`Removed draft "${title || targetId}".`);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="title-short-page">
      <PageHeader
        eyebrow="AI CREATION"
        title="Title to AI Short"
        description="Enter any title — AI researches verified sources, writes the full spoken script, and prepares 9:16 scenes."
        action={<Link className="button button-secondary" to="/title-to-short" onClick={()=>{request.current=null;}}>New short</Link>}
      />
      <div className="title-short-info">Vertical 9:16 • 30, 45 or 60 seconds • Local Celebrity Vault + Real Web Photos • Zero AI Images</div>
      {error&&<div className="notice notice-error" role="alert">{error}</div>}

      {!id&&<form className="studio-card" onSubmit={create}>
        <div className="studio-field">
          <label className="studio-label" htmlFor="short-title">Long Video Title or Topic</label>
          <textarea
            id="short-title"
            required
            minLength={5}
            maxLength={500}
            rows={3}
            placeholder="e.g. Iman Shumpert GOES OFF On Gilbert Arenas & Swaggy P — DEFENDS Steph Curry!"
            value={form.title}
            onChange={e=>setForm({...form,title:e.target.value})}
          />
          <span className="vault-helper-text">AI automatically researches reliable sources and generates your complete focused Short script.</span>
        </div>

        <div className="studio-controls-grid">
          <div className="studio-field">
            <label className="studio-label" htmlFor="create-duration">Duration</label>
            <select id="create-duration" value={form.duration} onChange={e=>setForm({...form,duration:Number(e.target.value)})}>
              {[30,45,60].map(v=><option key={v} value={v}>{v} seconds</option>)}
            </select>
          </div>
          <div className="studio-field">
            <label className="studio-label" htmlFor="create-language">Language</label>
            <select id="create-language" value={form.language} onChange={e=>setForm({...form,language:e.target.value})}>
              {['English','Urdu','Roman Urdu'].map(v=><option key={v}>{v}</option>)}
            </select>
          </div>
          <div className="studio-field">
            <label className="studio-label" htmlFor="create-style">Style</label>
            <select id="create-style" value={form.style} onChange={e=>setForm({...form,style:e.target.value})}>
              {['educational','storytelling','documentary'].map(v=><option key={v}>{v}</option>)}
            </select>
          </div>
        </div>

        <div className="studio-controls-grid">
          <div className="studio-field">
            <label className="studio-label" htmlFor="create-media-source">Media Source</label>
            <select id="create-media-source" value={form.media_mode||'online'} onChange={e=>setForm({...form,media_mode:e.target.value,online_fallback:false})}>
              <option value="online">Celebrity Folder + Real Web Photos</option>
              <option value="local">Local Library Only</option>
              <option value="mixed">Mixed</option>
            </select>
          </div>
          <div className="studio-field">
            <label className="studio-label" htmlFor="create-media-pref">Visual Preference</label>
            <select id="create-media-pref" value={form.media_preference||'mix_both'} onChange={e=>setForm({...form,media_preference:e.target.value})}>
              <option value="mix_both">Mix Both (Images + Short Clips)</option>
              <option value="prefer_clips">Prefer Video Clips (.mp4/.mov/.webm)</option>
              <option value="prefer_images">Prefer Images (.jpg/.png/.webp)</option>
            </select>
          </div>
        </div>

        {['local','mixed'].includes(form.media_mode)&&<div className="studio-field">
          <label className="studio-label" htmlFor="create-collection">Personal Collection</label>
          <select id="create-collection" required value={form.collection_id||''} onChange={e=>setForm({...form,collection_id:e.target.value})}>
            <option value="">Choose collection</option>
            {collections.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>}

        {form.media_mode==='mixed'&&<label className="studio-checkbox-row">
          <input type="checkbox" checked={!!form.online_fallback} onChange={e=>setForm({...form,online_fallback:e.target.checked})}/>
          <span>Allow real web photo fallback when no suitable local image is found</span>
        </label>}

        <div className="studio-controls-grid">
          <div className="studio-field">
            <label className="studio-label" htmlFor="create-narrator">Narrator Engine</label>
            <select id="create-narrator" value={form.narrator||'automatic'} onChange={e=>updateVoiceSettings(false,{narrator:e.target.value,voice:e.target.value==='gemini_tts'?'Charon':''})}>
              {capabilities?.voices?.some(v=>v.provider==='gemini_tts')&&<option value="gemini_tts">Gemini AI Studio (Natural · Style / Pace / Accent)</option>}
              <option value="automatic">Automatic configured narrator</option>
              <option value="kokoro_onnx">Kokoro Neural (English only)</option>
              <option value="local">Installed system narrator</option>
              {capabilities?.voices?.some(v=>v.provider==='elevenlabs')&&<option value="elevenlabs">ElevenLabs</option>}
            </select>
          </div>
          {renderVoiceSelect(false)}
        </div>

        <div className="studio-field">
          <label className="studio-label" htmlFor="source-urls">Optional YouTube / Article Source URLs (one per line)</label>
          <textarea id="source-urls" rows={3} value={sourceText} onChange={e=>setSourceText(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." />
          <span className="vault-helper-text">Paste a YouTube or article URL to read its script/transcript first and turn it into a cohesive Short Story, matching named personalities with your local Celebrity Folder.</span>
        </div>

        {capabilities?.languages[form.language]?.available===false&&<div role="alert" className="notice notice-error">{capabilities.languages[form.language].message}</div>}
        <Button type="submit" disabled={!capabilities||capabilities.languages[form.language]?.available===false} loading={busy}>
          Research &amp; Generate Script
        </Button>
      </form>}

      {id&&!draft&&!error&&<p role="status">Loading draft…</p>}

      {draft&&(() => {
        const scriptLines = (texts.length ? texts : (draft.scenes || []).map((s) => s.narration))
          .map((s) => String(s || '').trim())
          .filter(Boolean);
        const combinedScript = scriptLines.join('\n\n');
        const scriptWords = combinedScript.split(/\s+/).filter(Boolean).length;
        const wpsMap = { rapid: 2.45, fast: 2.35, normal: 2.25, measured: 2.05 };
        const estWps = wpsMap[draft.voice_pace || 'normal'] || 2.25;
        const scriptEstSec = Math.round(scriptWords / estWps);
        return <>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,flexWrap:'wrap',marginTop:16}}>
          <h2 style={{margin:0}}>{draft.title}</h2>
          {canRemoveDraft(draft)&&(
            <Button variant="danger" disabled={running} onClick={()=>removeDraft(draft.id, draft.title, true)}>
              <Trash2 size={14} /><span>Remove Draft</span>
            </Button>
          )}
        </div>

        <p>{draft.duration}s target · {draft.language} · {draft.style} · Draft version {draft.revision}</p>
        <ol className="title-short-progress" aria-label="Generation progress">
          {steps.map(([key,label],index)=><li key={key} aria-current={key===stage?'step':undefined} className={key===stage?'current':stageIndex>index||draft.status==='ready'?'done':''}>{label}{key===stage&&running?'…':''}</li>)}
        </ol>
        <div role="status" className="title-short-info">
          {draft.status==='analyzing'
            ? `Step 1/3: Understanding topic & preparing web research (${elapsedSec}s)…`
            : ['researching','research_verification'].includes(draft.status)
            ? `Step 2/3: Researching & verifying reliable sources (${elapsedSec}s)…`
            : draft.status==='script'
            ? `Step 3/3: Writing your full Short script (${elapsedSec}s)…`
            : draft.status==='visuals' && !draft.video_url
            ? `Matching Celebrity Vault & visual clips for your script (${elapsedSec}s)…`
            : draft.status==='script_review'
            ? 'Research complete — your full script and storyboard are ready below.'
            : draft.status==='ready'
            ? 'Short ready for preview and direct MP4 download.'
            : draft.status==='failed'
            ? 'Generation stopped. Saved drafts and earlier renders are preserved.'
            : draft.status.replaceAll('_',' ')}
        </div>
        {draft.research_failure_code&&<p role="status"><b>{draft.research_failure_code==='search_failed'?'Search service unavailable':draft.research_failure_code==='analysis_service_failed'?'AI evidence service unavailable':'Evidence insufficient'}</b> — saved script edits and prior renders are preserved.</p>}
        {draft.ai_fallback_mode&&<div role="status" className="title-short-info" style={{marginBottom:12}}><b>Source-grounded quota fallback active:</b> Live AI hit its rate limit, so this draft was assembled directly from fetched real sources. Review and edit the narration below before rendering.</div>}
        {draft.error_message&&<div role="alert" className="notice notice-error">
          <div>{draft.error_message}</div>
          {/quota|rate limit|429/i.test(draft.error_message)&&<div style={{marginTop:10,display:'flex',gap:8,flexWrap:'wrap'}}>
            <Link className="button button-secondary" to="/settings">Open AI Quota &amp; Backup Providers (Extra Keys / Groq / Ollama)</Link>
          </div>}
        </div>}

        {draft.status==='failed'&&<section className="studio-card" style={{marginBottom:20}}>
          <div className="studio-field">
            <label className="studio-label" htmlFor="retry-sources">Reliable Source URLs (one per line)</label>
            <textarea id="retry-sources" rows={3} value={sourceText} onChange={e=>setSourceText(e.target.value)} />
          </div>
          <div style={{display:'flex',gap:10,flexWrap:'wrap'}}>
            <Button disabled={running||dirty} onClick={()=>action('/'+id+'/sources',{revision:draft.revision,source_urls:sourceText.split(/\n/).map(s=>s.trim()).filter(Boolean)})}>Verify URLs and retry research</Button>
            {['research_verification','script'].includes(draft.failed_step)&&draft.sources.length>0&&<Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/retry?refresh_sources=false',{revision:draft.revision})}>Recheck retrieved facts and write script</Button>}
            <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/retry',{revision:draft.revision})}>Retry automatic research (preserve edits)</Button>
          </div>
        </section>}

        {!!draft.scenes.length&&<section className="studio-card script-summary-card" style={{marginBottom:20}}>
          <div className="studio-card-head">
            <div>
              <h3 style={{margin:0,display:'flex',alignItems:'center',gap:8}}>
                <FileText size={18} />
                <span>Generated Script</span>
              </h3>
              <p className="vault-helper-text" style={{margin:'4px 0 0'}}>
                {scriptWords} words · ~{scriptEstSec}s spoken ({draft.duration}s target · {draft.language})
              </p>
            </div>
            <div className="studio-action-row">
              <Button
                variant="secondary"
                type="button"
                onClick={() => {
                  navigator.clipboard?.writeText(combinedScript).then(() => setReviewNotice('Copied generated script to clipboard.')).catch(() => {});
                }}
              >
                <Copy size={14} />
                <span>Copy Script</span>
              </Button>
              <Button
                disabled={running||dirty||['failed','in_progress'].includes(draft.research_state)}
                onClick={renderShort}
              >
                {running&&['validating','visuals','voiceover','rendering'].includes(draft?.status)?`Rendering (${draft.status} · ${elapsedSec}s)…`:'Render 9:16 Short'}
              </Button>
            </div>
          </div>
          {reviewNotice&&!draft.video_url&&<div className="notice notice-success" role="status" style={{marginBottom:12}}>{reviewNotice}</div>}
          <div className="generated-script-body" dir={draft.language==='Urdu'?'rtl':'ltr'}>
            {draft.scenes.map((sc,idx)=>(
              <p key={sc.number} className="generated-script-line">
                <span className="script-scene-tag">Scene {String(sc.number).padStart(2,'0')}</span>
                <span>{texts[idx]??sc.narration}</span>
              </p>
            ))}
          </div>
        </section>}

        {!!draft.scenes.length&&<section className="title-short-panel">
          <h3>Interactive Scene Storyboard</h3>
          <p className="vault-helper-text" style={{marginBottom:16}}>
            {draft.status==='ready'?'Scene times follow the final narration.':'Scene times are estimates until final narration supplies native timestamps.'}
          </p>

          {draft.scenes.map((scene,i)=>(
            <article className="storyboard-card" key={scene.number}>
              <div>
                <div className="storyboard-head">
                  <span className="scene-badge">Scene {String(scene.number).padStart(2,'0')} · {scene.start.toFixed(1)}–{scene.end.toFixed(1)}s</span>
                  {scene.asset?.celebrity_name&&<span className="celeb-pill">{scene.asset.provider==='celebrity_vault'?`Local Vault: ${scene.asset.celebrity_name}`:scene.asset.celebrity_name}</span>}
                  {scene.asset?.provider&&scene.asset.provider!=='celebrity_vault'&&<span className="filter-pill" style={{height:24,fontSize:11,padding:'0 10px'}}>{scene.asset.provider}</span>}
                </div>

                <div className="studio-field">
                  <label className="studio-label" htmlFor={'narration-'+i}>Spoken Narration</label>
                  <textarea id={'narration-'+i} rows={3} maxLength={1500} dir={draft.language==='Urdu'?'rtl':'ltr'} disabled={running} value={texts[i]??scene.narration} onChange={e=>{const next=[...texts];next[i]=e.target.value;setDirty(true);setTexts(next);}} />
                </div>

                <p style={{fontSize:13,margin:'0 0 8px'}}><b>On-screen caption focus:</b> {scene.on_screen_text}</p>
                <p style={{fontSize:13,margin:'0 0 12px',color:'#475569'}}><b>Visual plan:</b> {scene.visual_description} · <i>{scene.image_query}</i></p>

                <div className="studio-controls-grid">
                  <div className="studio-field">
                    <label className="studio-label" htmlFor={'transition-'+i}>Transition Style</label>
                    <select id={'transition-'+i} disabled={running||dirty} value={scene.transition||'smoothleft'} onChange={e=>action('/'+id+'/scenes/'+scene.number+'/transition',{revision:draft.revision,transition:e.target.value},'PUT')}>
                      {[
                        ['smoothleft','Smooth Slide Left'],
                        ['slide','Slide Left'],
                        ['wipe','Wipe Left'],
                        ['flash','White Flash'],
                        ['zoomin','Zoom In Transition'],
                        ['radial','Radial Sweep'],
                        ['dissolve','Dissolve Fade'],
                        ['crossfade','Crossfade'],
                        ['cut','Hard Cut (0s)'],
                      ].map(([val,lbl])=><option key={val} value={val}>{lbl}</option>)}
                    </select>
                  </div>
                  <div className="studio-field">
                    <label className="studio-label" htmlFor={'scene-instruction-'+i}>Optional Visual / Rewrite Direction</label>
                    <input id={'scene-instruction-'+i} maxLength={500} placeholder="e.g. close up interview reaction" value={instructions[i]||''} disabled={running} onChange={e=>setInstructions({...instructions,[i]:e.target.value})} />
                  </div>
                </div>

                <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
                  <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/regenerate',{revision:draft.revision,instruction:instructions[i]||''})}>Regenerate visual</Button>
                  <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/rewrite',{revision:draft.revision,instruction:instructions[i]||''})}>Rewrite scene</Button>
                  <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,locked:!draft.scene_locks?.includes(scene.number)},'PUT')}>{draft.scene_locks?.includes(scene.number)?'Unlock':'Lock'}</Button>
                  {i>0&&<Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,swap_with:scene.number-1},'PUT')}>Move earlier</Button>}
                </div>
              </div>

              <div>
                <div className="storyboard-preview-frame">
                  {scene.preview_url
                    ? (scene.asset?.media_type==='video'
                        ? <video src={mediaUrl(scene.preview_url)} controls muted loop playsInline />
                        : <img src={mediaUrl(scene.preview_url)} alt={scene.asset?.note||scene.visual_description} />)
                    : <span style={{color:'#94a3b8',fontSize:12,padding:16,textAlign:'center'}}>No visual yet</span>}
                </div>
                <div className="storyboard-media-actions">
                  <Button variant="secondary" disabled={running||dirty||draft.scene_locks?.includes(scene.number)} onClick={()=>{setVaultSearch('');setVaultPickerScene(scene.number);}}>
                    <FolderOpen size={14} /><span>Pick from Vault</span>
                  </Button>
                  <label className="button button-secondary" style={{cursor:'pointer',margin:0}}>
                    <Upload size={14} /><span>Upload Local File</span>
                    <input type="file" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm" style={{display:'none'}} disabled={running||dirty||draft.scene_locks?.includes(scene.number)} onChange={e=>{if(e.target.files?.[0])uploadSceneMedia(scene.number,e.target.files[0]);}}/>
                  </label>
                  {localMedia.length>0&&<select aria-label={'Replace from library scene '+scene.number} value="" disabled={running||dirty||draft.scene_locks?.includes(scene.number)} onChange={e=>{if(e.target.value)action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,media_id:e.target.value},'PUT');}}>
                    <option value="">Library image…</option>
                    {localMedia.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>}
                </div>
              </div>
            </article>
          ))}

          <div className="studio-controls-grid" style={{marginTop:16}}>
            <div className="studio-field">
              <label className="studio-label" htmlFor="draft-narrator">Narrator Engine</label>
              <select id="draft-narrator" disabled={running||dirty} value={draft.narrator||'automatic'} onChange={e=>updateVoiceSettings(true,{narrator:e.target.value,voice:e.target.value==='gemini_tts'?'Charon':''})}>
                {capabilities?.voices?.some(v=>v.provider==='gemini_tts')&&<option value="gemini_tts">Gemini AI Studio (Natural · Style / Pace / Accent)</option>}
                <option value="automatic">Automatic configured narrator</option>
                <option value="kokoro_onnx">Kokoro Neural (High quality, English)</option>
                <option value="local">System Narrator (Instant &lt;1s, Offline)</option>
                {capabilities?.voices?.some(v=>v.provider==='elevenlabs')&&<option value="elevenlabs">ElevenLabs (Fast Cloud)</option>}
              </select>
            </div>
            {renderVoiceSelect(true)}
          </div>

          <div className="title-short-actions" style={{alignItems:'center'}}>
            <Button variant="secondary" disabled={running||!dirty} onClick={()=>action('/'+id+'/script',{revision:draft.revision,narrations:texts},'PUT')}>Save script edits</Button>
            {draft.media_mode!=='local'&&draft.scenes.some(s=>!s.preview_url)&&<Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/visuals',{revision:draft.revision})}>Fetch real photos / clips</Button>}
            <Button disabled={running||dirty||['failed','in_progress'].includes(draft.research_state)} onClick={renderShort}>
              {running&&['validating','visuals','voiceover','rendering'].includes(draft?.status)?`Rendering (${draft.status} · ${elapsedSec}s)…`:'Render 9:16 Short'}
            </Button>
            {(() => {
              const wc = texts.join(' ').trim().split(/\s+/).filter(Boolean).length;
              const est = Math.round(wc / estWps);
              return <span className="studio-hint" style={{fontSize:12,color:'#64748b'}}>{wc} words (~{est}s voice vs {draft.duration}s max)</span>;
            })()}
          </div>
          {running&&['validating','visuals','voiceover','rendering'].includes(draft?.status)&&(
            <div className="studio-alert" role="status" style={{marginTop:12,background:'#eff6ff',border:'1px solid #bfdbfe',color:'#1e3a8a'}}>
              {draft.status==='validating'&&`Step 1/4: Checking reviewed script & source alignment (${elapsedSec}s)...`}
              {draft.status==='visuals'&&`Step 2/4: Verifying scene photos & clips (${elapsedSec}s)...`}
              {draft.status==='voiceover'&&`Step 3/4: Generating voiceover & word-level timing (${elapsedSec}s)...`}
              {draft.status==='rendering'&&`Step 4/4: Compositing 9:16 video, transitions & captions via FFmpeg (${elapsedSec}s)...`}
            </div>
          )}
          {dirty&&<p role="status">Unsaved edits. Save the script before regenerating visuals or rendering.</p>}
        </section>}

        {draft.video_url&&<section className="studio-card" style={{marginBottom:20}}>
          <h3>Final 9:16 Preview &amp; Export</h3>
          <video className="title-short-video" key={draft.video_url} controls preload="metadata" src={mediaUrl(draft.video_url)} />
          <p>{draft.output_duration?.toFixed(2)}s actual · {draft.voice?.provider} · {draft.voice?.voice}</p>
          {reviewNotice&&<div className="notice notice-success" role="status">{reviewNotice}</div>}
          <div style={{display:'flex',gap:10,flexWrap:'wrap',alignItems:'center'}}>
            {canDownload && (
              <a className="button button-primary" href={mediaUrl(draft.video_url+'&download=true')} download={`short-${draft.id}.mp4`}>Download Final MP4</a>
            )}
            {canDownload && (
              <Button
                variant="secondary"
                type="button"
                onClick={() => {
                  const text = `${draft.title}\n\n${draft.script || ''}\n\n#Shorts`;
                  navigator.clipboard?.writeText(text).then(() => setReviewNotice('Copied Title & Script to clipboard.')).catch(() => {});
                }}
              >
                Copy Title &amp; Script
              </Button>
            )}
            {canRemoveDraft(draft) && (
              <Button variant="danger" disabled={busy} onClick={() => removeDraft(draft.id, draft.title, true)}>
                <Trash2 size={14} /><span>Remove Draft</span>
              </Button>
            )}
            <a className="button button-secondary" href={mediaUrl(draft.credits_url+'&download=true')}>Download photo credits</a>
            <a className="button button-secondary" href={mediaUrl(draft.sources_url+'&download=true')}>Download research sources</a>
          </div>
        </section>}

        {draft.render_history.length>0&&<details className="title-short-panel"><summary>Preserved renders</summary>{draft.render_history.map(v=><p key={v.revision}>Version {v.revision}: <a href={mediaUrl(v.video_url)} target="_blank" rel="noreferrer">Preview</a>{canDownload && <> · <a href={mediaUrl(v.video_url+'&download=true')}>Download</a></>}</p>)}</details>}

        {(!!draft.sources.length||!!draft.research_diagnostics?.length||!!draft.research_candidates?.length||!!draft.primary_media?.length)&&(
          <details className="title-short-panel">
            <summary>Research sources &amp; verification details ({draft.sources.length} sources)</summary>
            {draft.sources.map(s=><details key={s.id}><summary>{s.id}: <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></summary><p>{s.excerpt}</p></details>)}
            {!!draft.claims?.length&&<details><summary>Claim support ({draft.claims.length})</summary>{draft.claims.map((c,i)=><p key={i}><b>{c.claim}</b> ({c.source_id})<br />{c.supporting_excerpt}</p>)}</details>}
            {!!draft.primary_media?.length&&<details><summary>Video/podcast leads ({draft.primary_media.length})</summary>{draft.primary_media.map((m,i)=><p key={i}><a href={m.url} target="_blank" rel="noreferrer">{m.title}</a> · {m.creator} ({m.transcript_status})</p>)}</details>}
            {!!draft.research_candidates?.length&&<details><summary>Candidate leads ({draft.research_candidates.length})</summary>{draft.research_candidates.map(s=><p key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> · {s.publisher_group}</p>)}</details>}
            {!!draft.research_diagnostics?.length&&<details><summary>Retrieval diagnostics ({draft.research_diagnostics.length})</summary>{draft.research_diagnostics.map((r,i)=><p key={i}>{r.stage}: {r.result||r.feed_title} {r.url} {r.error} {r.reason} {r.detail}</p>)}</details>}
          </details>
        )}
      </>;
      })()}

      {!id&&history.length>0&&<section className="studio-card" style={{marginTop:20}}>
        <h3 style={{marginTop:0}}>Recent Title Drafts</h3>
        {reviewNotice&&<div className="notice notice-success" role="status" style={{marginBottom:12}}>{reviewNotice}</div>}
        <div style={{display:'grid',gap:10}}>
          {history.map(row=>(
            <div key={row.id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,padding:'10px 12px',borderRadius:10,border:'1px solid var(--line)',background:'var(--surface-alt)'}}>
              <div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
                <Link to={'/title-to-short/'+row.id} style={{fontWeight:600}}>{row.title}</Link>
                <span className={'status-badge '+(row.video_url || row.status === 'ready' ? 'approved' : row.status)}>{row.video_url || row.status === 'ready' ? 'Ready MP4' : row.status.replaceAll('_',' ')}</span>
              </div>
              {canRemoveDraft(row)&&(
                <Button variant="danger" disabled={busy} onClick={()=>removeDraft(row.id, row.title, false)} title="Remove draft">
                  <Trash2 size={14} /><span>Remove</span>
                </Button>
              )}
            </div>
          ))}
        </div>
      </section>}

      {vaultPickerScene&&<div className="studio-modal-backdrop" role="dialog" aria-modal="true">
        <div className="studio-modal">
          <div className="studio-modal-header">
            <h3 style={{margin:0}}>Pick Celebrity Asset for Scene {vaultPickerScene}</h3>
            <Button variant="secondary" onClick={()=>setVaultPickerScene(null)}>Close</Button>
          </div>
          <div className="studio-field">
            <div className="studio-input-icon-wrap">
              <span className="studio-input-icon"><Search size={15}/></span>
              <input style={{paddingLeft:36}} placeholder="Filter celebrities..." value={vaultSearch} onChange={e=>setVaultSearch(e.target.value)} />
            </div>
          </div>
          {!vaultLibrary?.celebrities?.length
            ? <p>No celebrity assets indexed yet. Visit <Link to="/celebrity-library">Celebrity Folder</Link> to connect a folder.</p>
            : vaultLibrary.celebrities
                .filter(c=>!vaultSearch.trim()||c.celebrity_name.toLowerCase().includes(vaultSearch.trim().toLowerCase()))
                .map(c=><div key={c.celebrity_name} style={{marginTop:16}}>
                  <h4 style={{margin:'0 0 8px'}}>{c.celebrity_name} ({c.image_count} images · {c.video_count} clips)</h4>
                  <div className="vault-media-grid">
                    {c.assets.map(a=>(
                      <button key={a.id} type="button" className="vault-asset-card" style={{textAlign:'left',cursor:'pointer',padding:0}} onClick={()=>uploadSceneMedia(vaultPickerScene,null,a.id)}>
                        <div className="vault-media-thumb" style={{height:150}}>
                          {a.media_type==='video'
                            ? <video src={mediaUrl(a.preview_url)} muted preload="metadata" />
                            : <img src={mediaUrl(a.preview_url)} alt={a.file_name} />}
                        </div>
                        <div className="vault-asset-meta">
                          <strong>{a.file_name}</strong>
                          <span className="mood-tag" style={{marginTop:4,display:'inline-block'}}>{a.media_type}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>)}
        </div>
      </div>}
    </div>
  );
}
