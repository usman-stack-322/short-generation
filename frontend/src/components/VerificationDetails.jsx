export default function VerificationDetails({ value }) {
  if (!value) return null;
  const tone=value.passed?'verified':value.label==='High-risk hold'?'failed':'verification_required';
  return <dl className="detail-rows verification-details">
    <div><dt>Verification</dt><dd><span className={`status-pill status-${tone}`}>{value.label}</span></dd></div>
    <div><dt>Risk</dt><dd>{value.risk_level}</dd></div>
    <div><dt>Source type</dt><dd>{value.source_category?.replaceAll('_',' ')}</dd></div>
    <div><dt>Sources</dt><dd>{value.source_count}</dd></div>
    <div><dt>Independent sources</dt><dd>{value.independent_source_count}</dd></div>
    <div><dt>Reason</dt><dd>{value.reason}</dd></div>
  </dl>;
}
