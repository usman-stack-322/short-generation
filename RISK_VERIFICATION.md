# Risk-based topic verification

Stories retain freshness, relevance, rumor, credibility and history checks.
Failed verification stops at `verification_required`; no demo content is substituted.

| Risk | Minimum corroboration |
| --- | --- |
| LOW | One explicitly configured authoritative primary publication within its topic/path scope, or two independent credible sources |
| MEDIUM | Two independent credible sources, including an official source plus an independent credible source where applicable |
| HIGH | Two independent credible sources; no single-source exception |

Sensitive wording takes priority over low-risk keywords. Numeric disagreements and
explicit contradictions remain on hold even when two publishers are present.
Unclassified stories default to MEDIUM. Risk classification and RSS corroboration
are conservative screening, not proof that every claim is true; content approval
is still mandatory before publishing.

## Configurable authority

`backend/app/research/sources.json` replaces the previous domain-to-score table.
Optional `RESEARCH_SOURCES_FILE` selects another local registry (paths resolve
against backend). Each entry includes exact hosts, editorial publisher group,
category, verified identity, reliability, primary publication paths and allowed
authoritative topic types. Categories are official_primary, major_news,
specialist_news and unknown.

Registry entries are trusted administrator configuration: verify publisher identity,
its editorial organization and its primary publication scope before granting
authority. RSS-supplied scores or category claims cannot promote themselves.
Unknown sources remain below the credibility threshold. The default major-news
entries have no single-source primary scope. Consequently a lone Guardian analysis
still needs corroboration; this change does not force that earlier job to pass.
Google News publisher metadata cannot grant the single-primary-source exception
without an actual primary publication URL.

## Independence

Reports are grouped conservatively using canonical URLs (tracking parameters/AMP
removed), identical normalized headlines, common publisher ownership, originating
wire attribution, shared extended quotations and highly similar substantial
summaries. Groups are transitive. BBC's two domains count as one publisher; two
publishers carrying the same Reuters report count once. Shared wording can cause a
conservative hold even when independent reporting is possible; adding truly
independent reporting is preferable to overriding the evidence count.

## Persistence and UI

Candidate JSON and new topic evidence retain the decision: risk, label, source
category, total sources, independent credible sources, duplicate signals and
reason. No schema migration is needed. Existing historical topic records are not
rewritten. Stored candidates are rechecked against current policy before becoming
new factual topics. The manual source-review endpoint cannot override failed
corroboration requirements.

Create Short research results and video review display Verified, Single
authoritative source, Needs second source, or High-risk hold, plus counts and reason.
Passing live candidates continue to the existing Gemini generation stage. Automated
pipeline tests verify that a single official low-risk candidate reaches that stage
and a high-risk one-source candidate does not call script generation.

## Validation

Policy fixtures cover official low-risk acceptance, medium-risk hold, independent
two-source acceptance, syndication grouping, high-risk hold and high-risk two-source
acceptance. Additional checks cover every duplicate signal, scoped authority,
untrusted source metadata, conflicts, stale evidence and manual bypass prevention.
The synthetic acceptance results are saved in
`generated/risk-verification-acceptance.json`; they are not newly researched news.

Run from backend: `..\.venv\Scripts\python.exe -m pytest -q`.
Run from frontend: `npm.cmd run build`.
YouTube uploads remain disabled.

Final checks: 143 backend tests passed, zero failed; one existing dependency
deprecation warning. Frontend production build passed.
