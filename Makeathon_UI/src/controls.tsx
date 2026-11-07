/** Shared form controls in the EthnoTrace style (2026-11-07): dropdown, filter picker, pager, expandable text. */
import { useEffect, useLayoutEffect, useRef, useState } from "react"

export type Option = { value: string; label: string; hint?: string }

function useOutside(ref: React.RefObject<HTMLElement | null>, onOutside: () => void, active: boolean) {
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
