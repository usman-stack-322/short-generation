import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import {PageHeader} from '../components/Shell';
import {Notice} from '../components/UI';
export default function UploadHistory(){
  const [rows,setRows]=useState([]),[error,setError]=useState('');
  useEffect(()=>{api('/videos').then(r=>setRows((Array.isArray(r)?r:r.items||[]).filter(j=>j.upload))).catch(e=>setError(e.message));},[]);
  return <><PageHeader title="Upload History" description="Private uploads to your own connected channels."/><Notice>{error}</Notice><section className="panel review-detail">{!rows.length&&<p>No upload jobs yet.</p>}{rows.map(j=><p key={j.id}><Link to={'/videos/'+j.id}>{j.topic}</Link> · {j.channel_name} · {j.upload.status.replaceAll('_',' ')}{j.upload.studio_url&&<> · <a href={j.upload.studio_url} target="_blank" rel="noreferrer">Open in YouTube Studio</a></>}</p>)}</section></>;
}
