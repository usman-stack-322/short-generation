import { useState } from 'react';
import { Button } from './UI';
import VoiceStyleSelect, { styleLabel } from './VoiceStyleSelect';

export default function VoiceDirection({ job, busy, canEdit, regenerate }) {
  const [selection, setSelection] = useState(null);
  const direction = job.voice_direction;
  const editable = canEdit && !['scheduled', 'uploading', 'uploaded'].includes(job.status);
  return <section className="panel review-detail"><h2>Voice Direction</h2>
    <span className="detail-label">PROVIDER / VOICE</span>
    <p>{job.language_name} ({job.voice_delivery?.locale || job.locale})</p>
    <p>{job.voice_provider || 'Pending'} · {job.narrator_voice || job.voice}</p>
    {direction ? <>
      <strong>{styleLabel(direction.style)}</strong>
      <p>{direction.tone.replaceAll('_', ' ')} · {direction.pace.toFixed(2)}x pace · {Math.round(direction.energy * 100)}% energy</p>
      <p className="muted">{direction.reason}</p>
      <small>{direction.auto_selected ? 'Automatically selected' : 'Manual override'}. Delivery depends on provider capabilities.</small>
      {job.voice_delivery?.provider === 'local' && <p className="muted">Local voice applies rate and volume; emotional and pitch controls are unavailable.</p>}
    </> : <p className="muted">Direction is selected when narration is generated.</p>}
    {editable && <><VoiceStyleSelect value={selection ?? job.voice_style ?? 'auto'} onChange={setSelection} disabled={busy}/>
      <Button variant="secondary" disabled={busy || !job.script} onClick={() => regenerate(selection ?? job.voice_style ?? 'auto')}>Regenerate Voice</Button>
      <small>Changing style regenerates narration and video, and requires approval again.</small></>}
  </section>;
}
