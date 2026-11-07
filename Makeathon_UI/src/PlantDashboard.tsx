import { useEffect, useState } from 'react'
import { friendly, studyLink, tierLabel } from './display'

type Item = Record<string, any>
type DashboardRecord = { entry: Item; book: Item; names: Item[]; candidates: Item[]; claims: Item[] }
type StudyResult = { items: Item[]; has_more: boolean }
const bookSources: Record<string, { name: string; url: string }> = {
  culpeper: { name: 'The Complete Herbal · Project Gutenberg', url: 'https://www.gutenberg.org/ebooks/49513' },
  dioscorides: { name: 'De materia medica · Wellmann edition', url: 'https://scaife.perseus.org/reader/urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1:1.preface.1-1.preface.5/' },
}

function ClaimCard({ row, source, onClaim }: {row: Item; source?: { name: string; url: string }; onClaim: (id: string) => void}) {
  const { claim, concepts } = row
  return <article className="dash-claim">
    <div className="dash-card-heading"><p className="dash-kicker">Historical statement</p><button onClick={() => onClaim(claim.id)}>View evidence →</button></div>
    <h4>{claim.claim_text || 'Historical claim'}</h4>
    {claim.quote && <blockquote>“{claim.quote}”</blockquote>}
    <div className="dash-tags">{concepts.map((c: Item, index: number) => c.id && /^D[0-9]+$/.test(c.id) ? <a key={index} href={`https://id.nlm.nih.gov/mesh/${c.id}`} target="_blank" rel="noreferrer">{c.name} · {friendly(c.match)} ↗</a> : <span key={index}>{c.name} · {friendly(c.match)}</span>)}</div>
    <div className="dash-source-row"><span>Source: {source ? <a href={source.url} target="_blank" rel="noreferrer">{source.name} ↗</a> : 'Historical record'}</span><button onClick={() => onClaim(claim.id)}>See quotation and context</button></div>
  </article>
}
function StudyCard({ row, onClaim }: {row: Item; onClaim: (id: string) => void}) {
  const a = row.assessment, s = row.study
  const link = studyLink(s, row.source_url)
  return <article className="dash-study">
    <div className="dash-card-heading"><p className="dash-kicker">{friendly(a.evidence_type)}</p><span className="dash-study-match">{friendly(a.applicability)}</span></div>
    <h4>{s.title || 'Untitled study'}</h4>
    <p className="dash-study-context">For <em>{row.candidate || 'candidate not linked'}</em> · {row.claim.claim_text || 'Historical claim'}</p>
    <p className="dash-study-finding">{friendly(a.finding)}{a.review_flag ? ' · Marked for review' : ''}</p>
    <div className="dash-source-row">{link ? <a href={link} target="_blank" rel="noreferrer">Open original source ↗</a> : <span>Source link not recorded</span>}<button onClick={() => onClaim(row.claim.id)}>View full assessment →</button></div>
  </article>
}
export default function PlantDashboard({ record, onCandidate, onClaim, onHistory, onResearch }: {
  record: DashboardRecord; onCandidate: (id: string, showHidden: boolean) => void; onClaim: (id: string) => void; onHistory: () => void; onResearch: () => void
}) {
  const [studies, setStudies] = useState<StudyResult | null>(null)
  const [studyError, setStudyError] = useState('')
  useEffect(() => {
    let active = true; setStudies(null); setStudyError('')
    fetch(`/api/entries/${record.entry.id}/studies`).then(async response => {
      if (!response.ok) throw new Error('Unable to load connected studies.')
      return response.json()
    }).then(result => { if (active) setStudies(result) }).catch(error => { if (active) setStudyError(error.message) })
    return () => { active = false }
  }, [record.entry.id])
  const source = bookSources[record.entry.book]
  const claims = record.claims.filter(c => c.concepts?.length)   // only claims mapped to a MeSH medical concept
  const shownClaims = claims.slice(0, 3), moreClaims = claims.slice(3)
  const shownStudies = studies?.items.slice(0, 3) || [], moreStudies = studies?.items.slice(3) || []
  const claimList = (items: Item[]) => items.map(row => <ClaimCard key={row.claim.id} row={row} source={source} onClaim={onClaim} />)
  const studyList = (items: Item[]) => items.map(row => <StudyCard key={row.assessment.id} row={row} onClaim={onClaim} />)
  return <div className="plant-dashboard">
    <section className="dash-names-section"><div className="dash-section-title"><div><p className="eyebrow">The names behind the record</p><h2>What was this plant called?</h2><p>Explore the proposed identifications and names recorded in the historical source.</p></div>{source && <a href={source.url} target="_blank" rel="noreferrer">Read the historical source ↗</a>}</div>
    <div className="dash-name-groups">
      <details className="dash-disclosure"><summary><span><small>MODERN BOTANICAL NAMES</small><strong>Scientific name candidates</strong></span><span>{record.candidates.length} <i aria-hidden="true">+</i></span></summary><div className="dash-disclosure-content"><p>These are hypotheses; a current scientific name does not prove a historical identification.</p>{record.candidates.length ? record.candidates.map(({hypothesis: h, decision: d}) => <div className="dash-name-row" key={h.id}><div><strong><em>{h.accepted_name || 'Name unresolved'}</em></strong><span className={`tier-pill tier-pill-${d?.tier || 'none'}`}>{tierLabel(d?.tier)}</span></div><button onClick={() => onCandidate(h.id, !['A','B'].includes(d?.tier))}>Sources and evidence →</button></div>) : <p>No scientific name candidates recorded.</p>}</div></details>
      <details className="dash-disclosure"><summary><span><small>NAMES IN THE SOURCE</small><strong>Historical and common names</strong></span><span>{record.names.length} <i aria-hidden="true">+</i></span></summary><div className="dash-disclosure-content"><p>Names and spellings associated with this historical entry; they are not necessarily modern common names.</p>{record.names.length ? record.names.map((n, i) => <div className="dash-name-row" key={i}><div><strong>{n.name || 'Name not recorded'}</strong><small>{friendly(n.layer)}</small>{n.quote && <p>“{n.quote}”</p>}</div><button onClick={onHistory}>View source →</button></div>) : <p>No additional historical names recorded.</p>}</div></details>
    </div></section>
    <section className="dash-content-section"><div className="dash-section-title"><div><p className="eyebrow">From the historical text</p><h2>Recorded historical claims</h2><p>Claims mapped to a medical concept (MeSH). These are historical statements, not proven effects.</p></div><button onClick={onResearch}>Explore every claim →</button></div>
      {claims.length ? <><div className="dash-cards">{claimList(shownClaims)}</div>{moreClaims.length > 0 && <details className="dash-more"><summary><span className="when-closed">Show {moreClaims.length} more historical claims</span><span className="when-open">Hide the {moreClaims.length} extra claims ↑</span></summary><div className="dash-cards">{claimList(moreClaims)}</div></details>}</> : <p className="dash-empty">No claim from this entry is mapped to a medical concept.</p>}
    </section>
    <section className="dash-content-section"><div className="dash-section-title"><div><p className="eyebrow">From the research record</p><h2>Modern studies</h2><p>Showing the closest recorded comparisons first. Assessments are automated and require review; a linked study does not establish effectiveness.</p></div><button onClick={onResearch}>Explore all research →</button></div>
      {studyError && <p className="dash-empty" role="alert">{studyError}</p>}{!studies && !studyError && <p className="dash-empty">Loading connected research…</p>}
      {studies && (studies.items.length ? <><div className="dash-cards">{studyList(shownStudies)}</div>{moreStudies.length > 0 && <details className="dash-more"><summary><span className="when-closed">Show {moreStudies.length} more connected assessments</span><span className="when-open">Hide the {moreStudies.length} extra assessments ↑</span></summary><div className="dash-cards">{studyList(moreStudies)}</div></details>}{studies.has_more && <p className="dash-empty">Showing the first 50 assessments. Open each claim to see its complete paginated research.</p>}</> : <p className="dash-empty">No studies have been assessed for this entry in the current dataset.</p>)}
    </section>
  </div>
}
