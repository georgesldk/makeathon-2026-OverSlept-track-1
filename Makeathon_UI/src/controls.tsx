/** Shared form controls in the EthnoTrace style (2026-11-07): dropdown, filter picker, pager, expandable text. */
import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { VoiceButton } from "./accessibility"

export type Option = { value: string; label: string; hint?: string }

export function useOutside(ref: React.RefObject<HTMLElement | null>, onOutside: () => void, active: boolean) {
  useEffect(() => {
    if (!active) return
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onOutside() }
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onOutside() }
    document.addEventListener("mousedown", handler); document.addEventListener("keydown", esc)
    return () => { document.removeEventListener("mousedown", handler); document.removeEventListener("keydown", esc) }
  }, [ref, onOutside, active])
}

/** A dropdown that looks like the rest of the site; options may carry a one-line explanation. */
export function Dropdown({ value, options, onChange, label, id, placeholder }: {
  value: string; options: Option[]; onChange: (v: string) => void; label?: string; id?: string; placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useOutside(box, () => setOpen(false), open)
  const current = options.find((o) => o.value === value)
  return (
    <div className={`dd${open ? " open" : ""}`} ref={box}>
      <button type="button" id={id} className="dd-button" aria-haspopup="listbox" aria-expanded={open} aria-label={label}
        onClick={() => setOpen(!open)}>
        <span className="dd-value">{current?.label || placeholder || "Choose"}</span>
        <span className="dd-chevron" aria-hidden="true">⌄</span>
      </button>
      <ul className="dd-menu" role="listbox" aria-label={label} hidden={!open}>
        {options.map((o) => (
          <li key={o.value} role="option" aria-selected={o.value === value}>
            <button type="button" className={o.value === value ? "selected" : ""} onClick={() => { onChange(o.value); setOpen(false) }}>
              <span className="dd-option-label">{o.label}</span>
              {o.hint && <span className="dd-option-hint">{o.hint}</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Quick-choice boxes for the most common values, plus a searchable list of all of them. */
export function FilterPicker({ value, onChange, items, placeholder, id, quick = 5 }: {
  value: string; onChange: (v: string) => void; items: { name: string; count: number }[]; placeholder: string; id: string; quick?: number
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useOutside(box, () => setOpen(false), open)
  const term = value.trim().toLowerCase()
  const matches = (term ? items.filter((i) => i.name.toLowerCase().includes(term)) : items).slice(0, 60)
  return (
    <div className="picker" ref={box}>
      <div className="picker-chips">
        {items.slice(0, quick).map((i) => (
          <button type="button" key={i.name} className={value === i.name ? "active" : ""}
            onClick={() => onChange(value === i.name ? "" : i.name)}>
            {i.name}<span>{i.count}</span>
          </button>
        ))}
      </div>
      <div className={`picker-field${open ? " open" : ""}`}>
        <input id={id} value={value} placeholder={placeholder} autoComplete="off"
          onFocus={() => setOpen(true)} onChange={(e) => { onChange(e.target.value); setOpen(true) }} />
        {value && <button type="button" className="picker-clear" aria-label="Clear" onClick={() => onChange("")}>×</button>}
        <button type="button" className="picker-toggle" aria-label="Show all choices" aria-expanded={open} onClick={() => setOpen(!open)}>⌄</button>
        {open && (
          <ul className="dd-menu picker-menu" role="listbox">
            {matches.length === 0 && <li className="picker-empty">No match</li>}
            {matches.map((i) => (
              <li key={i.name} role="option" aria-selected={value === i.name}>
                <button type="button" className={value === i.name ? "selected" : ""} onClick={() => { onChange(i.name); setOpen(false) }}>
                  <span className="dd-option-label">{i.name}</span><span className="picker-count">{i.count}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** Previous / page numbers / next. With a known total every page is reachable; otherwise the pages so far and the next one. */
export function Pager({ page, onPage, total, hasMore, label = "Pages" }: {
  page: number; onPage: (p: number) => void; total?: number; hasMore: boolean; label?: string
}) {
  const count = total !== undefined ? total : page + (hasMore ? 2 : 1)
  if (count <= 1) return null
  const pages: (number | "gap")[] = []
  for (let i = 0; i < count; i++) {
    if (i === 0 || i === count - 1 || Math.abs(i - page) <= 2) pages.push(i)
    else if (pages[pages.length - 1] !== "gap") pages.push("gap")
  }
  return (
    <nav className="pager" aria-label={label}>
      <button type="button" className="pager-step" disabled={page === 0} onClick={() => onPage(page - 1)}>‹ Previous</button>
      {pages.map((p, i) => p === "gap"
        ? <span key={`gap${i}`} className="pager-gap">…</span>
        : <button type="button" key={p} className={p === page ? "active" : ""} aria-current={p === page ? "page" : undefined} onClick={() => onPage(p)}>{p + 1}</button>)}
      {total === undefined && hasMore && <span className="pager-gap">…</span>}
      <button type="button" className="pager-step" disabled={page >= count - 1} onClick={() => onPage(page + 1)}>Next ›</button>
    </nav>
  )
}

/** Text clamped to a few lines that opens smoothly to its full length. */
export function ExpandableText({ text, className = "", lines = 4 }: { text: string; className?: string; lines?: number }) {
  const [open, setOpen] = useState(false)
  const [full, setFull] = useState(0)
  const [long, setLong] = useState(false)
  const ref = useRef<HTMLParagraphElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 24
    setFull(el.scrollHeight)
    setLong(el.scrollHeight > lineHeight * lines + 4)
  }, [text, lines])
  useEffect(() => setOpen(false), [text])
  return (
    <div className={`expandable-text${open ? " open" : ""}${long ? " long" : ""}`}>
      <p ref={ref} className={className} style={{ maxHeight: open ? full : `${lines * 1.7}em` }}
        onClick={() => long && setOpen(!open)}>{text}</p>
      {long && <button type="button" className="expandable-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Show less ↑" : "Read more ↓"}</button>}
    </div>
  )
}

/* ---------- Lenient search with suggestions (2026-11-07) ---------- */
export type Suggestion = { kind: "plant" | "use" | "family"; value: string; label: string; sub?: string; id?: string }

/** Lower-case, strip accents and Greek breathings, unify final sigma, so "μηον" finds "μῆον". */
export function fold(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ς/g, "σ").toLowerCase().trim()
}
function editDistance(a: string, b: string, max: number): number {
  if (Math.abs(a.length - b.length) > max) return max + 1
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]
    let best = i
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
      best = Math.min(best, cur[j])
    }
    if (best > max) return max + 1
    prev = cur
  }
  return prev[b.length]
}
/** Lower is better; Infinity = no match. Exact start, word start, substring, then typo-tolerant word match. */
export function matchScore(query: string, text: string): number {
  const q = fold(query), t = fold(text)
  if (!q) return Infinity
  if (t.startsWith(q)) return 0
  const words = t.split(/[\s,·()/-]+/).filter(Boolean)
  if (words.some((w) => w.startsWith(q))) return 1
  if (t.includes(q)) return 2
  if (q.length >= 3) {
    const max = q.length <= 4 ? 1 : 2
    let best = Infinity
    for (const w of words) {
      const d = editDistance(q, w.slice(0, Math.max(q.length, Math.min(w.length, q.length + 1))), max)
      if (d <= max) best = Math.min(best, 3 + d)
    }
    return best
  }
  return Infinity
}

const KIND_LABEL: Record<Suggestion["kind"], string> = { plant: "Plants", use: "Medical uses", family: "Plant families" }

/** A search field that suggests plants, medical uses and families as you type, forgiving typos. */
export function SearchBox({ value, onChange, onPick, onSubmit, suggestions, placeholder, label, id }: {
  value: string; onChange: (v: string) => void; onPick: (s: Suggestion) => void; onSubmit?: () => void
  suggestions: Suggestion[]; placeholder: string; label: string; id?: string
}) {
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(-1)
  const box = useRef<HTMLDivElement>(null)
  useOutside(box, () => setOpen(false), open)
  const groups = (["plant", "use", "family"] as const).map((kind) => ({
    kind,
    items: suggestions.filter((s) => s.kind === kind)
      .map((s) => ({ s, score: Math.min(matchScore(value, s.label), matchScore(value, s.sub || "") + 0.5) }))
      .filter((x) => x.score < Infinity)
      .sort((a, b) => a.score - b.score || a.s.label.length - b.s.label.length)
      .slice(0, kind === "plant" ? 6 : 4).map((x) => x.s),
  })).filter((g) => g.items.length)
  const flat = groups.flatMap((g) => g.items)
  const pick = (s: Suggestion) => { onPick(s); setOpen(false); setCursor(-1) }
  return (
    <div className={`search-box${open && value.trim() && flat.length ? " open" : ""}`} ref={box}>
      <span aria-hidden="true" className="search-box-icon">⌕</span>
      <input id={id} value={value} placeholder={placeholder} aria-label={label} autoComplete="off" role="combobox"
        aria-expanded={open && flat.length > 0}
        onFocus={() => setOpen(true)}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setCursor(-1) }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setCursor((c) => Math.min(flat.length - 1, c + 1)) }
          else if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(-1, c - 1)) }
          else if (e.key === "Enter") {
            // Enter takes the highlighted suggestion, or the best one, so a typo still finds its plant
            const choice = cursor >= 0 ? flat[cursor] : open && value.trim() ? flat[0] : undefined
            if (choice) pick(choice); else { onSubmit?.(); setOpen(false) }
          }
          else if (e.key === "Escape") setOpen(false)
        }} />
      {value && <button type="button" className="picker-clear" aria-label="Clear search" onClick={() => onChange("")}>×</button>}
      <VoiceButton onText={(t) => { onChange(t); setOpen(true); setCursor(-1) }} />
      {open && value.trim() && flat.length > 0 && (
        <div className="dd-menu search-menu" role="listbox">
          {groups.map((g) => (
            <div key={g.kind} className="search-group">
              <p className="search-group-label">{KIND_LABEL[g.kind]}</p>
              {g.items.map((s) => {
                const i = flat.indexOf(s)
                return (
                  <button type="button" key={`${s.kind}:${s.value}:${s.id || ""}`} role="option" aria-selected={i === cursor}
                    className={i === cursor ? "selected" : ""} onMouseEnter={() => setCursor(i)} onClick={() => pick(s)}>
                    <span className={`dd-option-label${s.kind === "plant" && s.sub ? "" : ""}`}>{s.label}</span>
                    {s.sub && <span className="dd-option-hint">{s.sub}</span>}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Builds the suggestion list from /api/names and /api/facets (shared by Explore and the Knowledge Map). */
export function buildSuggestions(names: { id: string; name?: string; book: string; chapter?: string; sci?: string; members?: number }[],
  facets: { families: { name: string; count: number }[]; concepts: { name: string; count: number }[] } | null,
  bookName: (b: string) => string): Suggestion[] {
  const out: Suggestion[] = []
  for (const n of names) {
    const where = `${bookName(n.book)}${n.chapter ? ` · ${n.chapter}` : ""}`
    if (n.name) out.push({ kind: "plant", value: n.name, id: n.id, label: n.name, sub: `${n.sci ? `${n.sci} · ` : ""}${where}` })
    if (n.sci) out.push({ kind: "plant", value: n.sci, id: n.id, label: n.sci, sub: `${n.name || ""} · ${where}` })
  }
  for (const c of facets?.concepts || []) out.push({ kind: "use", value: c.name, label: c.name, sub: `${c.count} entries` })
  for (const f of facets?.families || []) out.push({ kind: "family", value: f.name, label: f.name, sub: `${f.count} entries` })
  return out
}
