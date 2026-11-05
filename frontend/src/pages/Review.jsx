import SceneLayout from "../components/SceneLayout";
import ScenePhotos from "../components/ScenePhotos";
import JobLogs from "../components/JobLogs";
import SourceCard from "../components/SourceCard";
import VerificationDetails from "../components/VerificationDetails";
import LanguageSelect from "../components/LanguageSelect";
import { useLanguages } from "../hooks/useLanguages";
import VoiceDirection from "../components/VoiceDirection";
import PublishPanel from "../components/PublishPanel";
import { useState } from "react";
import { usePollingResource } from '../hooks/usePollingResource';
import { ArrowLeft, Check, Download, RotateCcw } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api, mediaUrl } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

const sections = ["hook", "context", "main_story", "why_it_matters", "ending"];
const progressLabels = {research_latest:"Researching latest news",research_7_days:"Searching the past 7 days",research_14_days:"Searching the past 14 days",research_evergreen:"Researching historical / evergreen stories",selecting_topic:"Selecting a fully verified topic",script_generation:"Generating script",voice_generation:"Generating narration",rendering:"Rendering video"};
const active = ["researching", "script_generation", "collecting_assets", "voice_generation", "rendering", "creating_cover", "uploading"];

export default function Review() {
  const { id } = useParams();
  const {data:job,setData:setJob,error:pollError}=usePollingResource(`/videos/${id}`);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [playbackDuration,setPlaybackDuration] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const [evergreen, setEvergreen] = useState(null);
  const [newLanguage, setNewLanguage] = useState(null);
  const { languages } = useLanguages();
  const textDirection = languages.find(item => item.code === job?.language_code)?.rtl ? "rtl" : "ltr";
  const role = localStorage.getItem("role");
  const running = job && active.includes(job.status);
  const researchReady = job?.status === 'research_ready';
  const researchFailed = job?.status === 'failed' && job?.failed_step === 'researching';
  const blocked = job?.status === "verification_required";

  async function action(name, scope, voiceStyle, language) {
    setBusy(true); setError("");
    try {
      const endpoint=(blocked || researchFailed) && name==='regenerate' && ['all','retry'].includes(scope) ? 'research' : name;
      setJob(await api(`/videos/${id}/${endpoint}`, {
        method: "POST", ...(scope ? { body: JSON.stringify({ scope, ...(voiceStyle ? { voice_style: voiceStyle } : {}), ...(language ? { language } : {}) }) } : {}),
      }));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function saveScript(event) {
    event.preventDefault(); setBusy(true);
    try {
      setJob(await api(`/videos/${id}/script`, { method: "PATCH", body: JSON.stringify(draft) }));
      setEditing(false);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function suggestEvergreen() {
    setBusy(true);setError('');
    try {setEvergreen(await api(`/videos/${id}/evergreen`,{method:'POST'}));}
    catch(err){setError(err.message);} finally{setBusy(false);}
  }
  if (!job && !error && !pollError) return <Loading />;
  if (!job) return <Notice>{error || pollError}</Notice>;
  return <>
    <Link to="/videos" className="back-link"><ArrowLeft size={15} /> Back to queue</Link>
    <PageHeader eyebrow="CONTENT REVIEW" title="Review your Short" description="Review the story, narration, sources, and metadata before approval."
      action={<span className={`status-pill status-${job.status}`}>{(researchReady ? (job.verification_status==='demo'?"Development topic ? ready to generate":"Verified ? ready to generate") : job.status.replaceAll("_", " "))}</span>} />
    <Notice>{error || pollError || (blocked && !job.error_message?.startsWith('No verified story found in the past 14 days.') && !job.error_message?.startsWith('No eligible verified news or historical story found.') ? 'No verified topic selected. Review candidate evidence or retry research.' : job.error_message)}</Notice>
    {running && <Notice type="info">Working: {progressLabels[job.current_step] || job.current_step.replaceAll("_", " ")}. Progress updates automatically. Local rendering may take a few minutes.</Notice>}
    {blocked && job.research_trace?.historical_search && <Notice type="info">
      Historical search: {job.research_trace.historical_search.attempted} source requests, {job.research_trace.historical_search.accessible} accessible.
      {job.research_trace.historical_search.budget_exhausted ? ' Research budget reached; some alternatives remain unattempted. Retry research or configure focused reference sources.' : ' All discovered eligible options were evaluated within the research budget.'}
      {job.research_trace.historical_search.attempted > 0 && job.research_trace.historical_search.accessible === 0 ? ' No source was accessible. Check network/provider access; this is not evidence that the stories are false.' : ' Candidate cards explain irrelevant stories and missing independent corroboration.'}
    </Notice>}
    {job.content_type==='historical' && <Notice type="info">Historical / evergreen story. {job.fallback_reason} This recounts a documented past event, not current news. Approval is still required.</Notice>}
    {job.warnings?.map(warning => <Notice type="info" key={warning}>{warning}</Notice>)}
    {job.verification_status==='limited_verification' && <Notice type="info">Limited verification — manual review required. This is not a verified news report. Review every supported claim and date before explicit approval. Publishing is blocked.</Notice>}
    {blocked && role!=='VIEWER' && <section className="panel review-detail"><h2>Alternative: sourced evergreen topic</h2><p>If current evidence is missing or unsafe, research a career-background topic separately. This does not generate a script or invent a current event.</p><Button variant="secondary" disabled={busy} onClick={suggestEvergreen}>Find sourced evergreen topic</Button>{evergreen && <><h3>{evergreen.title}</h3><p>{evergreen.summary}</p><a href={evergreen.source_url} target="_blank" rel="noreferrer">Review biography and original references</a><p>{evergreen.note}</p><small>Retrieved: {new Date(evergreen.retrieved_at).toLocaleString()}</small></>}</section>}
    <div className="review-layout">
      <section className="review-main">
        {mediaError && <section className="panel review-detail" role="alert"><h2>Saved video could not be loaded</h2><p>Refresh its access link. If the file is missing, check local storage before retrying the render.</p><Button variant="secondary" disabled={busy} onClick={async()=>{setBusy(true);try{setJob(await api(`/videos/${id}`));setMediaError(false);}catch(err){setError(err.message);}finally{setBusy(false);}}}>Refresh video link</Button><small>This reads the saved job without generating new content.</small></section>}
        {job.video_url ? <div className="video-player panel"><video key={job.video_url} controls playsInline onLoadedMetadata={event=>setPlaybackDuration(event.currentTarget.duration)} crossOrigin="use-credentials" onError={()=>setMediaError(true)} onLoadedData={()=>setMediaError(false)} poster={mediaUrl(job.thumbnail_url)} src={mediaUrl(job.video_url)}/><div className="video-player-meta"><span>{job.channel_name}</span><span>{playbackDuration ? playbackDuration.toFixed(2) : (job.output_duration || job.duration)}s</span></div></div> :
          <section className="panel review-empty"><h2>{researchReady ? (job.verification_status==='demo'?'Development topic selected':'Verified story selected') : blocked ? 'Verification required' : running ? 'Preparing your Short' : 'No video available'}</h2><p>{researchReady ? 'Research is complete. Choose Generate Short to start script, voice and video generation.' : blocked ? 'This story must pass source verification before script and video generation can continue.' : running ? 'Progress updates automatically as each stage completes.' : 'Check the job status and retry the failed step.'}</p></section>}
        {job.narration_url&&<section className="panel review-detail"><h2>Generated narration</h2><audio controls crossOrigin="use-credentials" src={mediaUrl(job.narration_url)}/><p>Per-video voiceover. Collection audio is managed separately in Media Library.</p></section>}
        <section className="panel script-panel" dir={textDirection} lang={job.locale}>
          <div className="panel-heading"><h2>Script</h2>
            {role !== "VIEWER" && job.script && !running && <Button variant="secondary" onClick={() => {
              setDraft(Object.fromEntries(sections.map(key => [key, job.script[key]]))); setEditing(!editing);
            }}>{editing ? "Cancel editing" : "Edit script"}</Button>}
          </div>
          {editing ? <form onSubmit={saveScript} className="form-stack">
            {sections.map(key => <label key={key}>{key.replaceAll("_", " ").toUpperCase()}<textarea dir={textDirection} lang={job.locale} className="script-editor" required value={draft[key] || ""} onChange={event => setDraft({ ...draft, [key]: event.target.value })} /></label>)}
            <Button type="submit" loading={busy}>Save script</Button>
            <small>Saving invalidates approval. Regenerate voice to update the video.</small>
          </form> : job.script ? <div className="script-sections">{sections.map(key => <div key={key}><span>{key.replaceAll("_", " ").toUpperCase()}</span><p>{job.script[key]}</p></div>)}</div> : <p>{researchReady ? 'Script generation has not started. Choose Generate Short when you are ready.' : blocked ? 'Script generation has not started: source verification is required. Review the candidate reasons below, then retry research when stronger evidence is available.' : job.status === 'failed' && job.failed_step === 'researching' ? 'Script generation has not started because research failed. Retry the research step.' : job.status === 'failed' && job.failed_step === 'script_generation' ? 'Script generation failed. Review the error above and retry the failed step; verified research will be reused.' : job.status === 'script_generation' ? 'Generating your script. Progress updates automatically.' : job.script_state === 'queued' ? 'Verified topic selected. Script generation is queued and will start automatically.' : 'Script generation is waiting for research to complete.'}</p>}
        </section>
        {role !== "VIEWER" && researchReady && <Button disabled={busy} onClick={()=>action('regenerate','all')}>Generate Short</Button>}
        {role !== "VIEWER" && !running && !researchReady && !["scheduled","uploaded"].includes(job.status) && <div className="regeneration-actions">
          {[['all','Regenerate all'],['script','Regenerate script'],['voice','Regenerate voice'],['video','Regenerate video'],['assets','Regenerate assets'],['cover','Regenerate cover'],['seo','Regenerate SEO'],['retry','Retry failed step']].map(([scope,label]) =>
            <Button key={scope} variant="secondary" disabled={busy || (blocked && !['all','retry'].includes(scope)) || (scope !== 'all' && scope !== 'retry' && !job.script)} title={blocked && !['all','retry'].includes(scope) ? 'Source verification must pass first' : undefined} onClick={() => action("regenerate",scope)}><RotateCcw size={14} />{blocked && scope === 'all' ? 'Research again' : blocked && scope === 'retry' ? 'Retry research' : label}</Button>)}
        </div>}
      </section>
      <aside className="review-aside">
        <section className="panel review-detail"><h2>Output language</h2><strong>{job.language_name}</strong><p className="muted">{job.locale}</p>
          {role !== 'VIEWER' && !['scheduled','uploading','uploaded'].includes(job.status) && <>
            <LanguageSelect value={newLanguage || job.language_code} onChange={setNewLanguage} disabled={busy || running || blocked}/>
            <Button variant="secondary" disabled={busy || running || blocked || !newLanguage || newLanguage === job.language_code} onClick={() => action('regenerate','script',null,newLanguage)}>Change language &amp; regenerate</Button>
            <small>Changing language regenerates script, voice, subtitles, SEO, cover and video. Approval is required again.</small>
          </>}
        </section>
          <section className="panel review-detail"><h2>Story details</h2><p>Content type: {job.content_type || "news"}</p><VerificationDetails value={blocked ? null : job.verification}/>{job.research_trace?.feed_errors?.length > 0 && <p>Some research feeds failed: {job.research_trace.feed_errors.join('; ')}. Check feed configuration or retry research later.</p>}<span className="detail-label">TOPIC</span><p>{job.topic || (blocked ? "No verified candidate selected" : running ? "Research in progress" : "No topic selected")}</p><span className="detail-label">PERSONALITY</span><p>{job.personality_name}</p>
          <span className="detail-label">SOURCES</span>{job.sources?.map((source,index) => {const option=job.draft_options?.find(item=>item.candidate_id===source.candidate_id);return <div key={index}><SourceCard source={source} headline={job.topic}/>{option && <><p>Ranking: {option.score}/100. {option.score_explanation}</p><p>{option.reason || option.missing_corroboration}</p>{blocked && role!=='VIEWER' && <Button variant="secondary" disabled={busy || !option.eligible} onClick={()=>action(`review-draft/${source.candidate_id}`)}>Generate review draft</Button>}<small>Source accessibility and main-claim support are checked again before generation.</small></>}</div>;})}
          {job.draft_review && <><p>Ranking: {job.draft_review.score}/100. {job.draft_review.score_explanation}</p><p>Missing corroboration: {job.draft_review.missing_corroboration}</p>{job.draft_review.sources?.map((source,index)=><p key={index}><a href={source.source_url} target="_blank" rel="noreferrer">{source.source_name}</a> · {source.published_at}</p>)}</>}
        </section>
        <VoiceDirection key={id} job={job} busy={busy || running} canEdit={role !== "VIEWER" && !blocked} regenerate={style => action("regenerate", "voice", style)} />
        {job.seo && <section dir={textDirection} lang={job.locale} className="panel review-detail"><h2>SEO metadata</h2><span className="detail-label">TITLE</span><p>{job.seo.title}</p><span className="detail-label">DESCRIPTION</span><p style={{whiteSpace:"pre-line"}}>{job.seo.description}</p><span className="detail-label">HASHTAGS</span><div className="tag-list">{job.seo.hashtags.map(tag => <span key={tag}>{tag}</span>)}</div><span className="detail-label">KEYWORDS</span><p>{job.seo.keywords.join(", ")}</p><span className="detail-label">COVER TEXT</span><strong className="cover-text-preview">{job.seo.cover_text}</strong></section>}
        {role === "OWNER" && <JobLogs id={id}/>}
        <PublishPanel job={job} onChange={setJob} onError={setError} />
        {job.video_url && <a className="download-link" href={`${mediaUrl(job.video_url)}&download=true`} download>Download MP4</a>}
        {job.thumbnail_url && <a className="download-link" href={`${mediaUrl(job.thumbnail_url)}&download=true`} download>Download vertical cover</a>}
        <section className="panel review-detail"><h2>Verification: {job.verification_status || "pending"}</h2>{job.evidence?.map((item,index)=><div className="source-card" key={index}><strong>{item.source_name}</strong><p>{item.title}</p><a href={item.source_url} target="_blank" rel="noreferrer">Review evidence ↗</a></div>)}</section>
        {job.scenes?.length > 0 && <section className="panel review-detail"><h2>Scene plan</h2>{job.scenes.map(scene=><details key={scene.scene_number}><summary>Scene {scene.scene_number}: {scene.start_time}–{scene.end_time}s</summary><p>{scene.narration}</p><small>{scene.visual_query}</small></details>)}</section>}
        {job.assets?.length > 0 && <ScenePhotos job={job} canEdit={role!=="VIEWER" && !blocked && !researchReady && !busy && !running && !["scheduled","uploaded"].includes(job.status)} onChange={setJob} onError={setError}/>}
        {job.assets?.length>0&&role!=="VIEWER"&&!blocked&&!researchReady&&!running&&!['scheduled','uploaded'].includes(job.status)&&<SceneLayout job={job} onChange={setJob} onError={setError}/>}

      </aside>
    </div>
  </>;
}
