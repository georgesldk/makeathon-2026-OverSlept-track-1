/**
 * Expert review (2026-11-07): domain experts confirm, dispute or annotate a plant identification, a claim,
 * a study assessment or a whole entry. Comments are stored by server.py in data/reviews.json (not in the
 * graph). Demo comments (demo=true) are generated for 24 entries and always labelled as such.
 */
import { useEffect, useMemo, useState } from "react"
import { Dropdown, SearchBox, type Suggestion } from "./controls"

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
  const r = await fetch(`/api/reviews${entryId ? `?entry_id=${entryId}` : ""}`)
  if (!r.ok) throw new Error(r.status === 404 ? "Reviews are not available: restart server.py." : "Reviews could not be loaded.")
  return r.json()
}

/** Agreement bar: share of confirmations among confirm + disagree votes; notes are counted but not scored. */
export function Score({ g }: { g: Item }) {
  const votes = g.confirm + g.disagree
  return (
    <div className="rv-score" title="Agreement = confirmations ÷ (confirmations + disagreements). Notes are not scored.">
      <div className="rv-bar">{votes > 0 && <><i className="ok" style={{ width: `${(100 * g.confirm) / votes}%` }} /><i className="no" style={{ width: `${(100 * g.disagree) / votes}%` }} /></>}</div>
      <span>{g.agreement != null ? `${g.agreement}% agree` : "no votes yet"} · {g.confirm} confirm · {g.disagree} disagree · {g.note} note{g.note === 1 ? "" : "s"}</span>
    </div>
  )
}

export function ReviewCard({ r, showTarget = true, openEntry }: { r: Review; showTarget?: boolean; openEntry?: (id: string) => void }) {
  return (
    <article className={`rv-card rv-${r.verdict}`}>
      <header>
        <span className={`rv-verdict rv-verdict-${r.verdict}`}>{VERDICT_LABEL[r.verdict]}</span>
        {r.demo && <span className="rv-demo" title="Generated example, not a real expert's opinion">Demo comment</span>}
        <span className="rv-who">{r.reviewer}{r.expertise ? ` · ${r.expertise}` : ""}</span>
        <time>{new Date(r.created_at).toLocaleDateString()}</time>
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
  return (
    <div className="rv-entry">
      {data.reviews.length === 0
        ? <p className="section-explanation">No expert has reviewed this entry yet.</p>
        : <>
            <Score g={data.summary.totals} />
            {data.summary.targets.map((g) => (
              <div className="rv-group" key={`${g.target_type}:${g.target_id}`}>
                <h4>{TARGET_LABEL[g.target_type as Review["target_type"]]}: <em>{g.target_label}</em>{g.demo_only && <span className="rv-demo">Demo comments</span>}</h4>
                <Score g={g} />
                {data.reviews.filter((r) => r.target_type === g.target_type && r.target_id === g.target_id).map((r) => <ReviewCard key={r.id} r={r} showTarget={false} />)}
              </div>
            ))}
          </>}
      <button type="button" className="primary-link" onClick={onAdd}>Add a review of this entry →</button>
    </div>
  )
}

/** The Expert review page: add a review, and see every review with its score. */
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
  const [reviewer, setReviewer] = useState(() => { try { return localStorage.getItem("rv-name") || "" } catch { return "" } })
  const [expertise, setExpertise] = useState(() => { try { return localStorage.getItem("rv-role") || "" } catch { return "" } })
  const [status, setStatus] = useState("")

  const refresh = () => loadReviews().then(setData).catch((e) => setError(e.message))
  useEffect(() => { refresh() }, [])
  const openForReview = async (id: string) => {
    setEntry(null); setStudies([]); setTarget(""); setStatus("")
    const r = await fetch(`/api/entries/${id}`)
    if (!r.ok) return setStatus("That entry could not be loaded.")
    const e = await r.json()
    setEntry(e); setSearch(e.entry.name || e.entry.label || "")
    fetch(`/api/entries/${id}/studies`).then((x) => x.json()).then((x) => setStudies(x.items || [])).catch(() => setStudies([]))
  }
  useEffect(() => { if (initialEntryId) openForReview(initialEntryId) }, [initialEntryId])

  const options = useMemo(() => {
    if (!entry) return []
    if (ttype === "identification") return entry.candidates.filter((c: Item) => ["A", "B"].includes(c.decision?.tier)).map((c: Item) => ({ value: c.hypothesis.id, label: c.hypothesis.accepted_name || "Unresolved", hint: c.decision?.tier === "A" ? "Meets identification criteria" : "Possible identification" }))
    if (ttype === "claim") return entry.claims.map((c: Item) => ({ value: c.claim.id, label: c.claim.claim_text, hint: c.concepts.map((x: Item) => x.name).join(", ") || "no medical concept" }))
    if (ttype === "study") return studies.map((s: Item) => ({ value: s.assessment.id, label: s.study.title || "Untitled study", hint: `for ${s.claim?.claim_text || "a claim"}` }))
    return [{ value: entry.entry.id, label: entry.entry.name || entry.entry.label }]
  }, [entry, ttype, studies])
  useEffect(() => { setTarget(ttype === "entry" && entry ? entry.entry.id : "") }, [ttype, entry])

  const submit = async () => {
    if (!entry || !target || !verdict || !comment.trim() || !reviewer.trim()) return setStatus("Choose what you are reviewing, a verdict, and write a comment and your name.")
    try { localStorage.setItem("rv-name", reviewer); localStorage.setItem("rv-role", expertise) } catch { /* private mode */ }
    const label = options.find((o: Item) => o.value === target)?.label || ""
    const r = await fetch("/api/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      entry_id: entry.entry.id, entry_name: entry.entry.name || entry.entry.label, book: entry.entry.book,
      target_type: ttype, target_id: target, target_label: label, verdict, comment, reviewer, expertise }) })
    if (!r.ok) return setStatus(r.status === 404 || r.status === 501
      ? "The API running now is an older version that cannot save reviews: restart server.py and try again."
      : (await r.json().catch(() => null))?.error || "The review could not be saved.")
    setComment(""); setVerdict(""); setStatus("Thank you: your review is saved.")
    refresh()
  }

  const shown = (data?.reviews || [])
  const summaryTargets = (data?.summary.targets || [])
  const t = data?.summary.totals
  return (
    <main className="standard-page review-page">
      <div className="section-head">
        <p className="eyebrow">Domain experts</p>
        <h1>Expert review</h1>
        <p>
          Domain experts can confirm, dispute or annotate a plant identification, a claim, a study assessment or a
          whole entry. Every comment appears on the plant's page, and each item gets an agreement score from the
          confirmations and disagreements it has received. Names are as given by reviewers; comments are stored
          with the site, separately from the research data.
        </p>
        <p className="rv-demo-note"><span className="rv-demo">Demo comment</span> marks generated examples for 24 plants, added to show how reviews look. They are not real expert opinions.</p>
      </div>
      {error && <p role="alert">{error}</p>}
      {t && (
        <dl className="rv-totals">
          <div><dt>Reviews</dt><dd>{t.reviews}</dd></div>
          <div><dt>Reviewers</dt><dd>{t.reviewers}</dd></div>
          <div><dt>Entries reviewed</dt><dd>{t.entries}</dd></div>
          <div><dt>Overall agreement</dt><dd>{t.agreement != null ? `${t.agreement}%` : "–"}</dd></div>
        </dl>
      )}
      <div className="rv-layout">
        <section className="rv-form">
          <h2>Add a review</h2>
          <label className="filter-label">1 · Find the plant</label>
          <SearchBox value={search} onChange={setSearch} suggestions={suggestions.filter((s) => s.kind === "plant")} label="Find a plant" placeholder="A plant's name"
            onPick={(s) => s.id && openForReview(s.id)} />
          {!suggestions.some((s) => s.kind === "plant") && (
            <p className="rv-status rv-warn">The plant list has not loaded, so no plant can be chosen. The API is probably an older version: restart server.py and reload this page.</p>
          )}
          {!entry && suggestions.some((s) => s.kind === "plant") && <p className="section-explanation">Type a name and pick it from the list (or press Enter for the best match).</p>}
          {entry && (
            <>
              <p className="rv-picked">{entry.entry.name || entry.entry.label} · {BOOK[entry.entry.book] || entry.entry.book}{entry.entry.label ? ` · ${entry.entry.label}` : ""}</p>
              <label className="filter-label">2 · What are you reviewing?</label>
              <div className="rv-choices">
                {(Object.keys(TARGET_LABEL) as Review["target_type"][]).map((k) => (
                  <button type="button" key={k} className={ttype === k ? "active" : ""} onClick={() => setTtype(k)}>{TARGET_LABEL[k]}</button>
                ))}
              </div>
              {ttype !== "entry" && (options.length
                ? <Dropdown label="Item to review" value={target} placeholder="Choose one" onChange={setTarget} options={options} />
                : <p className="section-explanation">Nothing of this kind is recorded for this entry.</p>)}
              <label className="filter-label">3 · Your verdict</label>
              <div className="rv-choices rv-verdicts">
                {(["confirm", "disagree", "note"] as const).map((v) => (
                  <button type="button" key={v} className={`rv-v-${v}${verdict === v ? " active" : ""}`} onClick={() => setVerdict(v)}>{v === "confirm" ? "✓ Confirm" : v === "disagree" ? "✕ Disagree" : "✎ Note"}</button>
                ))}
              </div>
              <label className="filter-label" htmlFor="rv-comment">4 · Comment</label>
              <textarea id="rv-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={5} maxLength={2000}
                placeholder="What do you confirm or dispute, and on what grounds (a reference, the text, field knowledge)?" />
              <div className="rv-who-fields">
                <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" maxLength={80} aria-label="Your name" />
                <input value={expertise} onChange={(e) => setExpertise(e.target.value)} placeholder="Your field (e.g. botanist)" maxLength={80} aria-label="Your field" />
              </div>
              <button type="button" className="primary-link" onClick={submit}>Submit review</button>
            </>
          )}
          {status && <p className="rv-status">{status}</p>}
        </section>
        <section className="rv-list">
          <div className="rv-list-head">
            <h2>All reviews</h2>
          </div>
          <h3 className="rv-sub">By item, most reviewed first</h3>
          <ul className="rv-targets">
            {summaryTargets.slice(0, 30).map((g) => (
              <li key={`${g.target_type}:${g.target_id}`}>
                <p><span className="rv-kind">{TARGET_LABEL[g.target_type as Review["target_type"]]}</span> <em>{g.target_label}</em>{g.demo_only && <span className="rv-demo">Demo</span>}</p>
                <button type="button" className="cite-link" onClick={() => openEntry(g.entry_id)}>{g.entry_name}{g.book ? ` · ${BOOK[g.book] || g.book}` : ""} →</button>
                <Score g={g} />
              </li>
            ))}
          </ul>
          <h3 className="rv-sub">Latest comments</h3>
          {shown.slice(0, 40).map((r) => <ReviewCard key={r.id} r={r} openEntry={openEntry} />)}
          {!shown.length && <p className="section-explanation">No comments to show.</p>}
        </section>
      </div>
    </main>
  )
}
