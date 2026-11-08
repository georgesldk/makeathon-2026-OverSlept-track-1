/**
 * Expert review (2026-11-07): domain experts confirm, dispute or annotate a plant identification, a claim,
 * a study assessment or a whole entry. Generated examples are labelled as demonstrations; submissions are disabled.
 */
import { useEffect, useState } from "react"
import { type Suggestion } from "./controls"
import { apiUrl } from "./api"

type Item = Record<string, any>
export type Review = {
  id: string; entry_id: string; entry_name?: string; book?: string; target_type: "identification" | "claim" | "study" | "entry"
  target_id: string; target_label?: string; verdict: "confirm" | "disagree" | "note"; comment: string; reviewer: string
  expertise?: string; created_at: string; demo?: boolean
}
type Summary = { targets: Item[]; totals: Item }
const TARGET_LABEL: Record<Review["target_type"], string> = { identification: "Plant identification", claim: "Claim", study: "Study assessment", entry: "Whole entry" }
const VERDICT_LABEL: Record<Review["verdict"], string> = { confirm: "Confirms", disagree: "Disagrees", note: "Note" }
const BOOK: Record<string, string> = { culpeper: "Culpeper", dioscorides: "Dioscorides", shennong: "Shennong Bencao Jing" }

export async function loadReviews(entryId?: string): Promise<{ reviews: Review[]; summary: Summary }> {
  const r = await fetch(apiUrl(`/api/reviews${entryId ? `?entry_id=${entryId}` : ""}`))
  if (!r.ok) throw new Error(r.status === 404 ? "Reviews are not available: restart server.py." : "Reviews could not be loaded.")
  return r.json()
}

export function ReviewCard({ r, showTarget = true, openEntry }: { r: Review; showTarget?: boolean; openEntry?: (id: string) => void }) {
  return (
    <article className={`rv-card rv-${r.verdict}`}>
      <header>
        <span className={`rv-verdict rv-verdict-${r.verdict}`}>{VERDICT_LABEL[r.verdict]}</span>
        {r.demo && <span className="rv-demo" title="Generated example, not a real expert's opinion">Demo comment</span>}
        <span className="rv-who">{r.reviewer}{r.expertise ? ` · ${r.expertise}` : ""}</span>
      </header>
      {showTarget && (
        <p className="rv-target">
          {TARGET_LABEL[r.target_type]}: <em>{r.target_label || r.target_id}</em>
          {openEntry && <> · <button type="button" className="cite-link" onClick={() => openEntry(r.entry_id)}>{r.entry_name || "entry"}{r.book ? ` (${BOOK[r.book] || r.book})` : ""} →</button></>}
        </p>
      )}
      <p className="rv-comment">{r.comment}</p>
    </article>
  )
}

/** The block shown on a plant page: this entry's reviews, grouped by what they review. */
export function EntryReviews({ entryId, onAdd }: { entryId: string; onAdd: () => void }) {
  const [data, setData] = useState<{ reviews: Review[]; summary: Summary } | null>(null)
  const [error, setError] = useState("")
  useEffect(() => {
    let active = true
    setData(null); setError("")
    loadReviews(entryId).then((d) => { if (active) setData(d) }).catch((e) => { if (active) setError(e.message) })
    return () => { active = false }
  }, [entryId])
  if (error) return <p className="section-explanation">{error}</p>
  if (!data) return <p className="section-explanation">Loading reviews…</p>
  const examples = data.reviews.filter((r) => r.demo === true)
  return (
    <div className="rv-entry">
      {examples.length === 0
        ? <p className="section-explanation">No demo reviews are available for this entry.</p>
        : <>
            {data.summary.targets.filter((g) => examples.some((r) => r.target_type === g.target_type && r.target_id === g.target_id)).map((g) => (
              <div className="rv-group" key={`${g.target_type}:${g.target_id}`}>
                <h4>{TARGET_LABEL[g.target_type as Review["target_type"]]}: <em>{g.target_label}</em><span className="rv-demo">Demo comments</span></h4>
                {examples.filter((r) => r.target_type === g.target_type && r.target_id === g.target_id).map((r) => <ReviewCard key={r.id} r={r} showTarget={false} />)}
              </div>
            ))}
          </>}
      <button type="button" className="primary-link" onClick={onAdd}>View demo reviews →</button>
    </div>
  )
}

/** Display illustrative reviews; submissions are disabled. */
export default function PeerReview({ openEntry }: {
  suggestions: Suggestion[]; openEntry: (id: string) => void; initialEntryId?: string
}) {
  const [data, setData] = useState<{ reviews: Review[]; summary: Summary } | null>(null)
  const [error, setError] = useState("")
  useEffect(() => { loadReviews().then(setData).catch((e) => setError(e.message)) }, [])

  const shown = (data?.reviews || []).filter((r) => r.demo === true)
  const summaryTargets = (data?.summary.targets || []).filter((g) => shown.some((r) => r.target_type === g.target_type && r.target_id === g.target_id))
  return (
    <main className="standard-page review-page">
      <div className="section-head">
        <p className="eyebrow">Demonstration only</p>
        <h1>Expert review demo</h1>
        <p>These generated examples illustrate how reviews could look. They are not real expert opinions or evidence of validation. Review submissions are disabled.</p>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="rv-layout rv-layout-demo">
        <section className="rv-list">
          <div className="rv-list-head">
            <h2>Example reviews</h2>
          </div>
          <h3 className="rv-sub">Example items</h3>
          <ul className="rv-targets">
            {summaryTargets.slice(0, 30).map((g) => (
              <li key={`${g.target_type}:${g.target_id}`}>
                <p><span className="rv-kind">{TARGET_LABEL[g.target_type as Review["target_type"]]}</span> <em>{g.target_label}</em><span className="rv-demo">Demo</span></p>
                <button type="button" className="cite-link" onClick={() => openEntry(g.entry_id)}>{g.entry_name}{g.book ? ` · ${BOOK[g.book] || g.book}` : ""} →</button>
              </li>
            ))}
          </ul>
          <h3 className="rv-sub">Example comments</h3>
          {shown.slice(0, 40).map((r) => <ReviewCard key={r.id} r={r} openEntry={openEntry} />)}
          {!shown.length && <p className="section-explanation">No comments to show.</p>}
        </section>
      </div>
    </main>
  )
}
