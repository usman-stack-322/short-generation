import { useEffect, useState, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, mediaUrl } from '../services/api';
import { PageHeader } from '../components/Shell';
import { Button } from '../components/UI';
import './TitleShort.css';

const active = new Set(['analyzing','researching','research_verification','script','validating','visuals','voiceover','rendering']);
const steps = [['analyzing','Analyze'],['researching','Research'],['script','Script review'],['visuals','Visuals'],['voiceover','Voiceover'],['rendering','Render']];
export default function TitleShort() {
  const { id } = useParams();
  const navigate = useNavigate();
  const request = useRef(null);
  const [form,setForm] = useState({title:'',duration:45,language:'English',style:'educational'});
  const [collections,setCollections]=useState([]),[channels,setChannels]=useState([]),[localMedia,setLocalMedia]=useState([]);
  useEffect(()=>{Promise.all([api('/library/collections'),api('/channels')]).then(([c,ch])=>{setCollections(c);setChannels(ch);}).catch(e=>setError(e.message));},[]);
  const [sourceText,setSourceText] = useState('');
  const [capabilities,setCapabilities] = useState(null);
  const [draft,setDraft] = useState(null);
  useEffect(()=>{if(draft?.collection_id)api('/library/collections/'+draft.collection_id+'/media?approved=true').then(setLocalMedia).catch(e=>setError(e.message));},[draft?.collection_id]);

  const [history,setHistory] = useState([]);
  const [texts,setTexts] = useState([]);
  const [instructions,setInstructions] = useState({});
  const [dirty,setDirty] = useState(false);
  const [scopeConsent,setScopeConsent] = useState(false);
  useEffect(()=>setScopeConsent(false),[draft?.revision]);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  useEffect(()=>{api('/title-shorts/capabilities').then(setCapabilities).catch(e=>setError(e.message));},[]);
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
  async function action(path,body,method='POST') {
    setBusy(true);setError('');
    try {
      const row=await api('/title-shorts'+path,{method,body:JSON.stringify(body)});
      setDirty(false);setDraft(row);

      return row;
    } catch(e){setError(e.message);} finally{setBusy(false);}
  }
  // Start polling again when an action moves the current draft into a worker stage.
  useEffect(()=>{
    if(!draft||!active.has(draft.status))return;
    let live=true;
    const timer=setInterval(()=>api('/title-shorts/'+draft.id).then(row=>{if(live)setDraft(row);}).catch(e=>{if(live)setError(e.message);}),2000);
    return()=>{live=false;clearInterval(timer);};
  },[draft?.id,draft?.status]);
  async function create(event){event.preventDefault();const payload={...form,source_urls:sourceText.split(/\n/).map(s=>s.trim()).filter(Boolean)};const fingerprint=JSON.stringify(payload);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,id:crypto.randomUUID()};const row=await action('',{...payload,request_id:request.current.id});if(row)navigate('/title-to-short/'+row.id);}
  const rawStage=draft?.status==='failed'?draft.failed_step:draft?.status;
  const stage=rawStage==='research_verification'?'researching':['script_review','validating'].includes(rawStage)?'script':rawStage;
  const stageIndex=steps.findIndex(([key])=>key===stage);
  return <div className="title-short-page">
    <PageHeader eyebrow="AI CREATION" title="Title to AI Short" description="One title. One compelling angle. A researched short you review before rendering." action={<Link className="button button-secondary" to="/title-to-short" onClick={()=>{request.current=null;}}>New short</Link>} />
    <div className="title-short-info">Vertical 9:16 • 30, 45 or 60 seconds • Sources kept separately • Uploads disabled</div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {!id&&<form className="title-short-panel" onSubmit={create}>
      <label htmlFor="short-title">Video title or topic</label>
      <textarea id="short-title" required minLength={5} maxLength={500} rows={3} placeholder="The Complete History of Artificial Intelligence" value={form.title} onChange={e=>setForm({...form,title:e.target.value})} />
      <p>A broad title becomes one focused question, fact or story, rather than a compressed long video.</p>
      <div className="title-short-controls">
        <label>Duration<select aria-label="Duration" value={form.duration} onChange={e=>setForm({...form,duration:Number(e.target.value)})}>{[30,45,60].map(v=><option key={v} value={v}>{v} seconds</option>)}</select></label>
        <label>Language<select aria-label="Language" value={form.language} onChange={e=>setForm({...form,language:e.target.value})}>{['English','Urdu','Roman Urdu'].map(v=><option key={v}>{v}</option>)}</select></label>
        <label>Style<select aria-label="Style" value={form.style} onChange={e=>setForm({...form,style:e.target.value})}>{['educational','storytelling','documentary'].map(v=><option key={v}>{v}</option>)}</select></label>
      </div>
      <label>Media source<select value={form.media_mode||'online'} onChange={e=>setForm({...form,media_mode:e.target.value,online_fallback:false})}><option value="online">Online Sources</option><option value="local">Local Library</option><option value="mixed">Mixed</option></select></label>
      {['local','mixed'].includes(form.media_mode)&&<label>Personal collection<select required value={form.collection_id||''} onChange={e=>setForm({...form,collection_id:e.target.value})}><option value="">Choose collection</option>{collections.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
      {form.media_mode==='mixed'&&<label><input type="checkbox" checked={!!form.online_fallback} onChange={e=>setForm({...form,online_fallback:e.target.checked})}/> Allow online fallback when no suitable local image is found</label>}
      <label>My channel (optional until upload)<select value={form.channel_id||''} onChange={e=>setForm({...form,channel_id:e.target.value||null})}><option value="">Choose later</option>{channels.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <p>Local photos illustrate scenes; they never verify script claims. Confirm people and topic tags in Media Library.</p>
      <label htmlFor="source-urls">Optional reliable source URLs (one per line)</label><textarea id="source-urls" rows={3} value={sourceText} onChange={e=>setSourceText(e.target.value)} placeholder="https://primary-institution.example/article" /><p>URLs are fetched and verified with the same rules as automatic research. At least two independently originating readable sources are required; syndicated copies count once.</p>
      <label>Narrator<select aria-label="Narrator" value={form.narrator||'automatic'} onChange={e=>setForm({...form,narrator:e.target.value})}><option value="automatic">Automatic configured narrator</option><option value="local">Installed system narrator</option><option value="kokoro_onnx">Reviewed Kokoro (English only)</option></select></label>
      {capabilities?.languages[form.language]?.available===false&&<div role="alert" className="notice notice-error">{capabilities.languages[form.language].message}</div>}
      <Button type="submit" disabled={!capabilities||capabilities.languages[form.language]?.available===false} loading={busy}>Research and draft short</Button>
      <p>Research finds supporting sources and creates an editable scene plan. Rendering waits for your review.</p>
    </form>}
    {id&&!draft&&!error&&<p role="status">Loading draft…</p>}
    {draft&&<>
      <h2>{draft.title}</h2>
      {draft.scope?.required&&<section className="title-short-panel" aria-label="Revised scope review"><h3>Revised scope — acceptance required</h3><p><b>Original input (preserved):</b> {draft.title}</p><p><b>Proposed video title:</b> {draft.scope.proposed_title}</p><p><b>Focused angle:</b> {draft.scope.focus}</p><h4>Omitted because evidence is insufficient</h4>{draft.scope.omissions.map((o,i)=><p key={i}><b>{o.claim}</b> — {o.reason}</p>)}<p>Only independently supported paraphrases are included. Missing transcripts do not block those paraphrases; exact spoken quotes are omitted.</p>{draft.scope_accepted?<p role="status">Revised scope and current saved script accepted. Editing or new research requires acceptance again.</p>:<><label className="title-short-scope-consent"><input type="checkbox" aria-label="Accept revised scope" checked={scopeConsent} disabled={running||dirty} onChange={e=>setScopeConsent(e.target.checked)} /> I accept the revised title, focused scope, omissions and current saved script.</label><Button disabled={running||dirty||!scopeConsent||draft.status!=='script_review'} onClick={()=>action('/'+id+'/scope/accept',{revision:draft.revision})}>Accept revised scope and script</Button><p>Review the complete script below before accepting. Rendering is a separate action.</p></>}</section>}<p>{draft.duration}s target · {draft.language} · {draft.style} · Draft version {draft.revision}</p>
      <ol className="title-short-progress" aria-label="Generation progress">{steps.map(([key,label],index)=><li key={key} aria-current={key===stage?'step':undefined} className={key===stage?'current':stageIndex>index||draft.status==='ready'?'done':''}>{label}{key===stage&&running?'…':''}</li>)}</ol>
      <div role="status" className="title-short-info">{draft.status==='script_review'?'Review and edit the narration below. Rendering starts only when you choose Render reviewed short.':draft.status==='ready'?'Short ready for preview and download. Listen and review before sharing.':draft.status==='failed'?'Generation stopped. Saved drafts and earlier renders are preserved.':draft.status.replaceAll('_',' ')}</div>
      {draft.research_failure_code&&<p role="status"><b>{draft.research_failure_code==='search_failed'?'Search service unavailable':draft.research_failure_code==='analysis_service_failed'?'AI evidence service unavailable':'Evidence insufficient'}</b> — saved script edits and prior renders are preserved.</p>}
      {draft.error_message&&<div role="alert" className="notice notice-error">{draft.error_message}</div>}
      {draft.status==='failed'&&<section className="title-short-panel"><label htmlFor="retry-sources">Reliable source URLs (one per line)</label><textarea id="retry-sources" rows={3} value={sourceText} onChange={e=>setSourceText(e.target.value)} /><Button disabled={running||dirty} onClick={()=>action('/'+id+'/sources',{revision:draft.revision,source_urls:sourceText.split(/\n/).map(s=>s.trim()).filter(Boolean)})}>Verify URLs and retry research</Button></section>}
      {!!draft.research_diagnostics?.length&&<details className="title-short-panel"><summary>Retrieval diagnostics</summary>{draft.research_diagnostics.map((r,i)=><p key={i}>{r.stage}: {r.result||r.feed_title} {r.url} {r.error} {r.reason} {r.detail}</p>)}</details>}
      {draft.status==='failed'&&['research_verification','script'].includes(draft.failed_step)&&draft.sources.length>0&&<Button disabled={running||dirty} onClick={()=>action('/'+id+'/retry?refresh_sources=false',{revision:draft.revision})}>Recheck retrieved claims and propose supported scope</Button>}
      {draft.status==='failed'&&<Button disabled={running||dirty} onClick={()=>action('/'+id+'/retry',{revision:draft.revision})}>Retry automatic research (preserve edits)</Button>}
      {!!draft.research_candidates?.length&&<details className="title-short-panel"><summary>Readable research candidates (not automatically verified)</summary>{draft.research_candidates.map(s=><p key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a><br />Publisher/origin: {s.publisher_group} · {s.independence_group||'unassessed'}</p>)}</details>}
      {!!draft.primary_media?.length&&<section className="title-short-panel"><h3>Video/podcast leads (authenticity not assumed)</h3>{draft.primary_media.map((m,i)=><p key={i}><a href={m.url} target="_blank" rel="noreferrer">{m.title}</a> · {m.creator}<br />{m.transcript_status} · Metadata does not verify speech.</p>)}</section>}
      {draft.evidence_review&&<section className="title-short-panel"><h3>Incident evidence review</h3><p>{draft.evidence_review.reason}</p>{!!draft.evidence_review.verified_claims?.length&&<details><summary>Supported context (does not verify the complete title)</summary>{draft.evidence_review.verified_claims.map((c,i)=><p key={i}><b>{c.claim}</b><br />{c.evidence.map((e,j)=><span key={j}><a href={draft.sources.find(s=>s.id===e.source_id)?.url} target="_blank" rel="noreferrer">{e.source_id}, passage {e.passage_id}</a>{j<c.evidence.length-1?' · ':''}</span>)}</p>)}</details>}{draft.evidence_review.quote_checks?.map((q,i)=><p key={i}><b>{q.quote}: {q.verified?'wording/attribution verified':'unverified — excluded'}</b><br />{q.reason}</p>)}{draft.evidence_review.missing_evidence?.map((m,i)=><p key={i}>{m}</p>)}</section>}
      {draft.analysis&&<section className="title-short-panel"><h3>{draft.research_state==='verified'?'Selected angle':'Proposed angle'}</h3>{!draft.sources.length&&<p>Research must confirm this angle before a script can be written.</p>}<strong>{draft.analysis.angle}</strong><p>{draft.analysis.rationale}</p><p><b>Viewer intent:</b> {draft.analysis.viewer_intent}</p></section>}
      {!!draft.sources.length&&<section className="title-short-panel"><h3>Research sources</h3><p>{draft.research_state==='failed'?'Previous or candidate sources: latest research has not passed verification.':'Readable source text was checked. Review origin groups and factual support before rendering.'}</p>{draft.sources.map(s=><details key={s.id}><summary>{s.id}: <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></summary><p>{s.excerpt}</p></details>)}<details><summary>Claim support</summary>{draft.claims.map((c,i)=><p key={i}><b>{c.claim}</b> ({c.source_id})<br />{c.supporting_excerpt}</p>)}</details></section>}
      {!!draft.scenes.length&&<section className="title-short-panel"><h3>Review script and scenes</h3><p>{draft.status==='ready'?'Scene times follow the final narration.':'Scene times are estimates until final narration supplies native timestamps.'} On-screen summaries are planning notes; the video uses box-free synchronized narration captions.</p>
        {draft.scenes.map((scene,i)=><article className="title-short-scene" key={scene.number}>
          <div><h4>Scene {scene.number} · {scene.start.toFixed(1)}–{scene.end.toFixed(1)}s</h4>
            <label htmlFor={'narration-'+i}>Narration</label><textarea id={'narration-'+i} rows={4} maxLength={1500} dir={draft.language==='Urdu'?'rtl':'ltr'} disabled={running} value={texts[i]??scene.narration} onChange={e=>{const next=[...texts];next[i]=e.target.value;setDirty(true);setTexts(next);}} />
            <p><b>On-screen summary:</b> {scene.on_screen_text}</p><p><b>Visual plan:</b> {scene.visual_description}</p>
            <p><b>Photo query:</b> {scene.image_query}<br /><b>Motion:</b> {scene.motion.replaceAll('_',' ')} · {scene.transition}</p>
            <details><summary>AI image prompt (plan only)</summary><p>{scene.ai_image_prompt}</p><p>AI image generation is not configured. A prompt is not a generated asset or historical evidence.</p></details>
            <label htmlFor={'scene-instruction-'+i}>Optional regeneration direction</label><input id={'scene-instruction-'+i} maxLength={500} value={instructions[i]||''} disabled={running} onChange={e=>setInstructions({...instructions,[i]:e.target.value})} />
            <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/regenerate',{revision:draft.revision,instruction:instructions[i]||''})}>Regenerate this scene visual</Button> <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/rewrite',{revision:draft.revision,instruction:instructions[i]||''})}>Rewrite only this scene</Button>
          </div>
          <div><label>Replace from my library<select value="" disabled={running||dirty||draft.scene_locks?.includes(scene.number)} onChange={e=>{if(e.target.value)action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,media_id:e.target.value},'PUT');}}><option value="">Select approved image</option>{localMedia.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
          <Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,locked:!draft.scene_locks?.includes(scene.number)},'PUT')}>{draft.scene_locks?.includes(scene.number)?'Unlock image':'Lock image'}</Button>
          <Button variant="secondary" disabled={running||dirty||draft.scene_locks?.includes(scene.number)} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,exclude:true},'PUT')}>Exclude image</Button>
          {i>0&&<Button variant="secondary" disabled={running||dirty} onClick={()=>action('/'+id+'/scenes/'+scene.number+'/local-image',{revision:draft.revision,swap_with:scene.number-1},'PUT')}>Move image earlier</Button>}
          </div>
          <div>{scene.preview_url?<><img src={mediaUrl(scene.preview_url)} alt={scene.asset?.note||scene.visual_description} /><p><a href={scene.asset.source_url} target="_blank" rel="noreferrer">Photo source</a> · {scene.asset.license}<br />{scene.asset.creator}</p><small>{scene.asset.note}</small></>:<p className="title-short-placeholder">Visual not retrieved yet. Generated prompts are not presented as finished visuals.</p>}</div>
        </article>)}
        <div className="title-short-actions"><Button variant="secondary" disabled={running||!dirty} onClick={()=>action('/'+id+'/script',{revision:draft.revision,narrations:texts},'PUT')}>Save script edits</Button><Button disabled={running||dirty||!draft.scope_accepted||['failed','in_progress'].includes(draft.research_state)} onClick={()=>action('/'+id+'/render',{revision:draft.revision})}>Render reviewed short</Button></div>
        {dirty&&<p role="status">Unsaved edits. Save the script before regenerating visuals or rendering. Changes are checked against sources again.</p>}
      </section>}
      {draft.video_url&&<section className="title-short-panel"><h3>Final preview</h3><video className="title-short-video" key={draft.video_url} controls preload="metadata" src={mediaUrl(draft.video_url)} /><p>{draft.output_duration?.toFixed(2)}s actual · {draft.voice?.provider} · {draft.voice?.voice}</p>{draft.voice?.roman_urdu_note&&<p>{draft.voice.roman_urdu_note}</p>}<a className="button button-primary" href={mediaUrl(draft.video_url+'&download=true')}>Download MP4</a> <a className="button button-secondary" href={mediaUrl(draft.credits_url+'&download=true')}>Download photo credits</a> <a className="button button-secondary" href={mediaUrl(draft.sources_url+'&download=true')}>Download research sources</a></section>}
      {draft.status==='ready'&&draft.video_url&&<form className="title-short-panel form-stack" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);try{const result=await api('/title-shorts/'+id+'/finalize',{method:'POST',body:JSON.stringify({revision:draft.revision,channel_id:f.get('channel'),title:f.get('title'),description:f.get('description')})});navigate('/videos/'+result.job_id);}catch(err){setError(err.message);}finally{setBusy(false);}}}><h3>Prepare for approval and private upload</h3><label>Destination channel<select name="channel" required defaultValue={draft.channel_id||''}><option value="">Choose my channel</option>{channels.map(c=><option key={c.id} value={c.id}>{c.name} ({c.youtube_channel_id||'not connected'})</option>)}</select></label><label>Video title<input name="title" required maxLength={100} defaultValue={(draft.scope?.proposed_title||draft.title).slice(0,100)}/></label><label>Description<textarea name="description" required maxLength={4000} defaultValue={draft.analysis?.angle||draft.title}/></label><Button loading={busy}>Review rendered video for approval</Button><p>Approval and private upload remain separate actions on the video review page.</p></form>}
      {draft.render_history.length>0&&<details className="title-short-panel"><summary>Preserved renders</summary>{draft.render_history.map(v=><p key={v.revision}>Version {v.revision}: <a href={mediaUrl(v.video_url)} target="_blank" rel="noreferrer">Preview</a> · <a href={mediaUrl(v.video_url+'&download=true')}>Download</a></p>)}</details>}
    </>}
    {!id&&history.length>0&&<section className="title-short-panel"><h3>Recent title drafts</h3>{history.map(row=><p key={row.id}><Link to={'/title-to-short/'+row.id}>{row.title}</Link> · {row.status.replaceAll('_',' ')}</p>)}</section>}
  </div>;
}
