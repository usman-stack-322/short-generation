import { useState } from 'react';
import { api } from '../services/api';
import { Button, Notice, Modal } from './UI';

export default function PublishPanel({job,onChange,onError}) {
  const [confirm,setConfirm]=useState(false),[revision,setRevision]=useState(null),[kids,setKids]=useState(''),[busy,setBusy]=useState(false);
  async function action(name,body={}) {
    setBusy(true);
    try {await api(`/videos/${job.id}/${name}`,{method:'POST',body:JSON.stringify(body)});onChange(await api(`/videos/${job.id}`));setConfirm(false);}
    catch(e){onError(e.message);}finally{setBusy(false);}
  }
  return <section className="approval-card"><strong>Approval and private upload</strong>
    <p>Review research, scenes, narration and metadata before approval. Changes require fresh approval.</p>
    {job.status==='ready_for_review'&&<Button loading={busy} onClick={()=>action('approve',{content_revision:job.content_revision})}>Approve reviewed video</Button>}
    {['approved','upload_failed'].includes(job.status)&&!job.upload?.youtube_video_id&&job.upload?.status!=='upload_uncertain'&&<Button disabled={busy} onClick={()=>{setRevision(job.content_revision);setKids('');setConfirm(true);}}>Upload Privately to YouTube</Button>}
    {job.upload&&<><p>Upload: {job.upload.status==='uploaded'?'Uploaded privately — review and publish in YouTube Studio.':job.upload.status.replaceAll('_',' ')} · {Math.round((job.upload.progress||0)*100)}%</p>
      <Notice>{job.upload.error_message}</Notice>
      {['processing','visibility_verification_failed'].includes(job.upload.status)&&<Button disabled={busy} onClick={()=>action('verify-upload')}>Check processing and private visibility</Button>}
      {job.upload.status==='pending'&&<Button disabled={busy} onClick={()=>action('resume-upload')}>Resume unsent private upload</Button>}
      {job.upload.studio_url&&<><a href={job.upload.studio_url} target="_blank" rel="noreferrer">Open in YouTube Studio</a> · <a href={job.upload.studio_fallback} target="_blank" rel="noreferrer">Channel content fallback</a></>}
      {job.upload.status==='upload_uncertain'&&<Button disabled={busy} onClick={()=>{const id=window.prompt('Inspect YouTube Studio and enter the existing video ID. Do not retry an uncertain upload.');if(id)action('reconcile-upload',{youtube_video_id:id.trim()});}}>Reconcile with existing video ID</Button>}
    </>}
    <Button variant="secondary" onClick={()=>navigator.clipboard.writeText((job.seo?.title||job.topic)+"\n\n"+(job.seo?.description||""))}>Copy metadata for manual upload</Button> <a href={job.upload?.studio_fallback||(job.youtube_channel_id?"https://studio.youtube.com/channel/"+job.youtube_channel_id+"/videos":"https://studio.youtube.com/")} target="_blank" rel="noreferrer">Open YouTube Studio for manual upload</a>
    <p>Private videos are still uploaded to YouTube. This workflow does not hide or change the uploader’s IP. Publish or schedule manually in Studio.</p>
    {confirm&&<Modal title="Confirm private upload" onClose={()=>setConfirm(false)}><form className="form-stack" onSubmit={e=>{e.preventDefault();action('upload',{content_revision:revision,confirmed:true,privacy_status:'private',made_for_kids:kids==='yes'});}}>
      <p>Destination: <strong>{job.channel_name}</strong><br/>Channel ID: {job.youtube_channel_id}<br/>Approved revision: {revision}</p>
      <p>{job.seo?.title||job.topic}</p><p>{job.seo?.description}</p>
      <Notice type="info">Always uploaded as Private. This is a private video, not a native Studio draft. Review any additional declarations in Studio before publishing.</Notice>
      <label>Is this video made for kids?<select required value={kids} onChange={e=>setKids(e.target.value)}><option value="">Choose explicitly</option><option value="no">No</option><option value="yes">Yes</option></select></label>
      <Button type="submit" loading={busy}>Confirm private upload</Button>
    </form></Modal>}
  </section>;
}
