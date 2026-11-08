/**
 * Expert review (2026-11-07): domain experts confirm, dispute or annotate a plant identification, a claim,
 * a study assessment or a whole entry. Generated examples are labelled as demonstrations; submissions are disabled.
 */
import { useEffect, useMemo, useState } from "react"
import { Dropdown, SearchBox, type Suggestion } from "./controls"
import { apiUrl } from "./api"

type Item = Record<string, any>
export type Review = {
  id: string; entry_id: string; entry_name?: string; book?: string; target_type: "identification" | "claim" | "study" | "entry"
  target_id: string; target_label?: string; verdict: "confirm" | "disagree" | "note"; comment: string; reviewer: string
  expertise?: string; created_at: string; demo?: boolean; preview?: boolean
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
      <p className="rv-comment">{r.preview ? r.comment : "[placeholder text]"}</p>
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

/** Illustrative reviews and a temporary, browser-only submission preview. */
export default function PeerReview({ suggestions, openEntry, initialEntryId = "" }: {
  suggestions: Suggestion[]; openEntry: (id: string) => void; initialEntryId?: string
}) {
  const [data, setData] = useState<{ reviews: Review[]; summary: Summary } | null>(null)
  const [error, setError] = useState("")
  const [search, setSearch] = useState("")
  const [entry, setEntry] = useState<Item | null>(null)
  const [studies, setStudies] = useState<Item[]>([])
  const [ttype, setTtype] = useState<Review["target_type"]>("identification")
  const [target, setTarget] = useState("")
  const [verdict, setVerdict] = useState<Review["verdict"] | "">("")
  const [comment, setComment] = useState("")
  const [reviewer, setReviewer] = useState("")
  const [expertise, setExpertise] = useState("")
  const [status, setStatus] = useState("")
  const [previews, setPreviews] = useState<Review[]>([])
  useEffect(() => { loadReviews().then(setData).catch((e) => setError(e.message)) }, [])

  const openForReview = async (id: string) => {
    setEntry(null); setStudies([]); setTarget(""); setStatus("")
    try {
      const r = await fetch(apiUrl(`/api/entries/${id}`))
      if (!r.ok) throw new Error()
      const e = await r.json()
      setEntry(e); setSearch(e.entry.name || e.entry.label || "")
      fetch(apiUrl(`/api/entries/${id}/studies`)).then((x) => x.json()).then((x) => setStudies(x.items || [])).catch(() => setStudies([]))
    } catch { setStatus("That entry could not be loaded.") }
  }
  useEffect(() => { if (initialEntryId) openForReview(initialEntryId) }, [initialEntryId])
  const options = useMemo(() => {
    if (!entry) return []
    if (ttype === "identification") return entry.candidates.filter((c: Item) => ["A", "B"].includes(c.decision?.tier)).map((c: Item) => ({ value: c.hypothesis.id, label: c.hypothesis.accepted_name || "Unresolved" }))
    if (ttype === "claim") return entry.claims.map((c: Item) => ({ value: c.claim.id, label: c.claim.claim_text }))
    if (ttype === "study") return studies.map((s: Item) => ({ value: s.assessment.id, label: s.study.title || "Untitled study" }))
    return [{ value: entry.entry.id, label: entry.entry.name || entry.entry.label }]
  }, [entry, ttype, studies])
  useEffect(() => { setTarget(ttype === "entry" && entry ? entry.entry.id : "") }, [ttype, entry])
  const submit = () => {
    if (!entry || !target || !verdict || !comment.trim() || !reviewer.trim()) return setStatus("Choose an item and verdict, and enter a comment and name.")
    const preview: Review = { id: `preview-${Date.now()}-${Math.random()}`, entry_id: entry.entry.id,
      entry_name: entry.entry.name || entry.entry.label, book: entry.entry.book, target_type: ttype, target_id: target,
      target_label: options.find((o: Item) => o.value === target)?.label || "", verdict, comment: comment.trim(),
      reviewer: reviewer.trim(), expertise: expertise.trim(), created_at: new Date().toISOString(), demo: true, preview: true }
    setPreviews((previous) => [preview, ...previous]); setComment(""); setVerdict("")
    setStatus("Demo preview added in this browser only. It is not submitted or saved and disappears when you leave this page or refresh.")
  }

  const shown = [...previews, ...(data?.reviews || []).filter((r) => r.demo === true)]
  const summaryTargets = (data?.summary.targets || []).filter((g) => shown.some((r) => r.target_type === g.target_type && r.target_id === g.target_id))
  return (
    <main className="standard-page review-page">
      <div className="section-head">
        <p className="eyebrow">Demonstration only</p>
        <h1>Expert review demo</h1>
        <p>These examples illustrate how reviews could look. They are not real expert opinions or evidence of validation. Anything you write is a temporary preview in this browser; it is not submitted or saved and disappears when you leave this page or refresh.</p>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="rv-layout">
        <section className="rv-form">
          <h2>Try a demo review</h2>
          <p className="section-explanation">For demonstration only. Your entry is not submitted or saved.</p>
          <label className="filter-label">1 · Find the plant</label>
          <SearchBox value={search} onChange={setSearch} suggestions={suggestions.filter((s) => s.kind === "plant")} label="Find a plant" placeholder="A plant's name" onPick={(s) => s.id && openForReview(s.id)} />
          {!entry && <p className="section-explanation">Type a name and select an entry.</p>}
          {entry && <>
            <p className="rv-picked">{entry.entry.name || entry.entry.label} · {BOOK[entry.entry.book] || entry.entry.book}</p>
            <label className="filter-label">2 · What are you reviewing?</label>
            <div className="rv-choices">{(Object.keys(TARGET_LABEL) as Review["target_type"][]).map((k) => <button type="button" key={k} className={ttype === k ? "active" : ""} onClick={() => setTtype(k)}>{TARGET_LABEL[k]}</button>)}</div>
            {ttype !== "entry" && (options.length ? <Dropdown label="Item to review" value={target} placeholder="Choose one" onChange={setTarget} options={options} /> : <p className="section-explanation">Nothing of this kind is recorded for this entry.</p>)}
            <label className="filter-label">3 · Your verdict</label>
            <div className="rv-choices rv-verdicts">{(["confirm", "disagree", "note"] as const).map((v) => <button type="button" key={v} className={`rv-v-${v}${verdict === v ? " active" : ""}`} onClick={() => setVerdict(v)}>{v === "confirm" ? "✓ Confirm" : v === "disagree" ? "✕ Disagree" : "✎ Note"}</button>)}</div>
            <label className="filter-label" htmlFor="rv-comment">4 · Comment</label>
            <textarea id="rv-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={5} maxLength={2000} placeholder="Write a demo comment" />
            <div className="rv-who-fields"><input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" maxLength={80} aria-label="Your name" /><input value={expertise} onChange={(e) => setExpertise(e.target.value)} placeholder="Your field (optional)" maxLength={80} aria-label="Your field" /></div>
            <button type="button" className="primary-link" onClick={submit}>Preview demo review</button>
          </>}
          {status && <p className="rv-status" role="status">{status}</p>}
        </section>
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
