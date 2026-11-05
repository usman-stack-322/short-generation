export default function SourceCard({ source, headline }) {
  const name=source.name.replace(/\s*\(RSS candidate; verification required\)/,'').split('|').at(-1).trim();
  return <article className="source-card"><strong>{name}</strong><dl className="detail-rows">
    <div><dt>Headline</dt><dd>{source.headline || headline || 'Source article'}</dd></div>
    <div><dt>Published</dt><dd>{source.published_at ? new Date(source.published_at).toLocaleString() : 'Date unavailable'}</dd></div>
    {source.event_date && <div><dt>Event date</dt><dd>{source.event_date_precision==='year' ? source.event_date.slice(0,4)+' (year only)' : source.event_date}</dd></div>}<div><dt>Reliability</dt><dd>{source.reliability_score ?? 'Not assessed'}</dd></div>
    </dl>{source.period_label && <p>{source.period_label}</p>}{source.reason && <p><strong>{source.status === 'rejected' ? 'Rejected' : 'Verification hold'}:</strong> {source.reason}</p>}{source.verification && <p>{source.verification.independent_source_count} independent source(s) · {source.verification.matched_source_count ?? source.verification.source_count} matching source(s)</p>}{source.url && <a href={source.url} target="_blank" rel="noreferrer">Open source &rarr;</a>}{source.supporting_sources?.filter(s=>s.url!==source.url).map((s,index)=><p key={index}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> · {s.published_at?new Date(s.published_at).toLocaleString():'Date unavailable'}</p>)}
  </article>;
}
