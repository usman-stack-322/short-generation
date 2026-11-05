import { useState,useEffect } from 'react';
import { api, mediaUrl } from '../services/api';
import { Button } from './UI';

export default function ScenePhotos({job,canEdit,onChange,onError}){
  const [pending,setPending]=useState(null);
  const [saved,setSaved]=useState([]);
  useEffect(()=>{let live=true;if(canEdit)api('/library/collections').then(async rows=>{const media=await Promise.all(rows.filter(c=>c.channel_id===job.channel_id).map(c=>api(`/library/collections/${c.id}/media?approved=true`)));if(live)setSaved(media.flat().filter(a=>a.personality_id===job.personality_id&&a.media_type==='photo'));}).catch(()=>{});return()=>{live=false;};},[job.id,canEdit]);
  async function edit(asset,action,body){
    setPending(asset.id);onError('');
    try{
      const options=body instanceof FormData?{method:'POST',body}:{method:'POST',body:JSON.stringify({revision:job.content_revision})};
      onChange(await api(`/videos/${job.id}/assets/${asset.id}/${action}`,options));
    }catch(error){onError(error.message);}finally{setPending(null);}
  }
  function upload(event,asset){
    event.preventDefault();const form=new FormData(event.currentTarget);form.set('revision',job.content_revision);
    edit(asset,'upload',form);
  }
  return <section className="panel review-detail"><h2>Scene photographs</h2>
    <p className="media-coverage" role="status">{job.assets.filter(a=>a.media_type==='photo').length} photos · {job.assets.filter(a=>a.media_type==='clip').length} clips · {job.assets.filter(a=>!['photo','clip'].includes(a.media_type)).length} held / legacy scenes · {job.assets.length} scenes</p>
    <p className="muted">Real photos only. Metadata checks cannot guarantee authenticity. Archive and illustrative photos do not prove the story. Changes require rendering and approval again.</p>
    {job.assets.some(asset=>asset.source==='pexels')&&<p><a href="https://www.pexels.com" target="_blank" rel="noreferrer">Photos provided by Pexels</a></p>}
    {job.assets.map(asset=><details key={asset.id} className="scene-photo"><summary>Scene {asset.scene_number} · {asset.label || asset.source}</summary>
      {asset.preview_url&&asset.media_type==='clip'&&<video controls crossOrigin="use-credentials" src={mediaUrl(asset.preview_url)}/>}
      {asset.preview_url&&asset.media_type!=='clip'&&<a href={mediaUrl(asset.preview_url)} target="_blank" rel="noreferrer" aria-label={`Preview scene ${asset.scene_number}`}><img crossOrigin="use-credentials" src={mediaUrl(asset.preview_url)} alt={`Scene ${asset.scene_number}: ${asset.label || asset.source}`} loading="lazy"/></a>}
      {asset.kind==='missing'&&<p role="alert">Scene held: {asset.note || 'Upload or replace genuine relevant media.'}</p>}
      <p>{asset.license} · {asset.creator || asset.source}</p><p>{asset.note}</p>
      {asset.url&&<a href={asset.url} target="_blank" rel="noreferrer">Photo source</a>}{asset.license_url&&<> · <a href={asset.license_url} target="_blank" rel="noreferrer">License terms</a></>}
      <p className="scene-credit">{asset.attribution}</p>
      {canEdit&&<><div className="regeneration-actions"><Button variant="secondary" disabled={!!pending} onClick={()=>edit(asset,'replace')}>{pending===asset.id?'Working…':'Find replacement'}</Button><Button variant="secondary" disabled={!!pending} onClick={()=>edit(asset,'remove')}>Remove photo</Button></div>
        <label>Choose saved photo<select value="" disabled={!!pending} onChange={async e=>{if(!e.target.value)return;setPending(asset.id);try{onChange(await api(`/videos/${job.id}/assets/${asset.id}/saved`,{method:'POST',body:JSON.stringify({revision:job.content_revision,media_id:e.target.value})}));onError('');}catch(e){onError(e.message);}finally{setPending(null);}}}><option value="">Select approved matching photo</option>{saved.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <details><summary>Upload licensed photo</summary><form className="form-stack" onSubmit={event=>upload(event,asset)}>
          <label>Photograph<input name="file" type="file" accept="image/jpeg,image/png,image/webp" required/></label>
          <label>Photographer<input name="creator" maxLength={200} required/></label>
          <label>Source page URL<input name="source_url" type="url" placeholder="https://…" maxLength={1000}/></label>
          <label>License<select name="license"><option>Own photograph</option><option>CC0</option><option>CC BY 4.0</option></select></label>
          <label><input name="rights_confirmed" type="checkbox" value="true" required/> I have rights to reuse and modify this photo.</label>
          <label><input name="real_photo_confirmed" type="checkbox" value="true" required/> This is an authentic photograph, not AI artwork, a face swap or a fabricated event.</label>
          <Button type="submit" disabled={!!pending}>Upload photo</Button>
        </form></details></>}
    </details>)}
  </section>;
}
