import { useState } from 'react';
import { api } from '../services/api';
import { Button,Notice } from './UI';
export default function JobLogs({id}){
  const [data,setData]=useState(null),[error,setError]=useState('');
  async function load(){try{setData(await api(`/videos/${id}/logs`));}catch(err){setError(err.message);}}
  return <section className="panel review-detail"><h2>Job logs</h2><Button variant="secondary" onClick={load}>Load logs</Button><Notice>{error}</Notice>
    {data&&<><p>Step: {data.step} / retries: {data.retry_count}</p>{data.error&&<p>{data.error}</p>}<pre className="job-log">{data.render_log || 'No renderer log recorded yet.'}</pre></>}
  </section>;
}
