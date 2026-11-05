import VerificationDetails from "./VerificationDetails";
import { useState } from 'react';
import { api } from '../services/api';
import { Button, Notice } from './UI';

export default function ResearchPicker({ channelId, personalityId, selected, onSelect, provider }) {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function research() {
    setBusy(true); setError(''); onSelect(null);
    try { setRows(await api('/research/candidates', { method:'POST', body:JSON.stringify({channel_id:channelId,personality_id:personalityId}) })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function verify(row) {
    const note = window.prompt('After reading at least two independent credible sources, explain what you verified (20+ characters).');
    if (!note) return;
    if (!window.confirm('Confirm that you reviewed the sources and checked the exact factual claims. This does not approve uploading.')) return;
    setBusy(true);
    try {
      await api(`/research/${row.id}/verify`, {method:'POST',body:JSON.stringify({confirmed:true,note})});
      setRows(old => old.map(item => item.id === row.id ? {...item,status:'verified',rejection_reason:null}:item));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <section className="research-picker">
    <Button type="button" variant="secondary" loading={busy} disabled={!channelId || !personalityId} onClick={research}>{provider==='demo'?'Explore development topics':'Research current sources'}</Button>
    <Notice>{error}</Notice>
    <p className="muted">{provider==='demo'?'Development educational angles only. These are not verified live news stories.':'Feed corroboration is a screening step. Sensitive claims require source review. No restricted pages are scraped.'}</p>
    <div className="research-results">{rows.map(row => <article key={row.id} className={`source-card ${selected === row.id ? 'selected-source':''}`}>
      <strong>{row.title}</strong><VerificationDetails value={row.verification}/><span className={`status-pill status-${row.status}`}>{row.status.replaceAll('_',' ')}</span>
      {row.provider==='demo'&&<p>Development example — not live news or a verified factual report.</p>}
      <p>{row.source_name} · Score {row.overall_score} · {row.published_at && new Date(row.published_at).toLocaleString()}</p>
      {row.period_label&&<p>{row.period_label}</p>}<small>{row.rejection_reason}</small>
      <div className="review-actions">{row.evidence?.map((source,index) => <a key={index} href={source.source_url} target="_blank" rel="noreferrer">Source {index+1}: {source.source_name} ↗</a>)}</div>
      {['verified','demo'].includes(row.status) && <Button type="button" variant="secondary" onClick={() => onSelect(row.id)}>{selected === row.id ? 'Selected':row.status==='demo'?'Use development topic':'Use this topic'}</Button>}
      {row.status === 'verification_required' && row.verification?.passed && <Button type="button" variant="secondary" disabled={busy} onClick={() => verify(row)}>Confirm source review</Button>}
    </article>)}</div>
  </section>;
}
