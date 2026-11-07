/**
 * Knowledge Map overview (2026-11-07): the whole graph at an abstract level, with drill-down.
 *   whole graph  : books -> plant families -> medical uses (MeSH)
 *   a book       : the families of its proposed plants
 *   a family     : its historical entries and the medical uses they record
 *   a use        : the families and the entries that record it
 *   an entry     : its own detailed map (handled by KnowledgeMap)
 * A breadcrumb trail and a Back button go up again. Edge width = number of historical entries.
 * Data: /api/overview (aggregate counts) and /api/entries (the entries of a family or use).
 */
import { useEffect, useMemo, useState } from "react"
import { apiUrl } from "./api"
import { Background, Controls, Position, ReactFlow, type Edge, type Node } from "@xyflow/react"
import FamilyIcon from "./FamilyIcon"

type Row = Record<string, any>
type Data = { book_family: Row[]; family_use: Row[]; use_research: Row[] }
export type Level = { kind: "all" } | { kind: "book" | "family" | "use"; value: string }
const BOOK_LABEL: Record<string, string> = { culpeper: "Culpeper", dioscorides: "Dioscorides", shennong: "Shennong Bencao Jing" }
const TOP_FAMILIES = 14
const TOP_USES = 16
const MAX_LINKS = 70
const MAX_ENTRIES = 40
const side = { sourcePosition: Position.Right, targetPosition: Position.Left }

const levelName = (l: Level) => (l.kind === "all" ? "Whole graph" : l.kind === "book" ? BOOK_LABEL[l.value] || l.value : l.value)
const heading = (id: string, x: number, text: string): Node => ({ id, position: { x, y: -60 }, className: "ov-heading", selectable: false, data: { label: text } })

export default function MapOverview({ book, path, setPath, onEntry }: {
  book: string; path: Level[]; setPath: (p: Level[]) => void; onEntry: (id: string) => void
}) {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState("")
  const [hover, setHover] = useState<string | null>(null)
  const [entries, setEntries] = useState<Row[] | null>(null)
  const level: Level = path[path.length - 1] || { kind: "all" }
  const levelValue = level.kind === "all" ? "" : level.value

  useEffect(() => {
    fetch(apiUrl("/api/overview")).then(async (r) => {
      if (r.ok) return r.json()
      const why = r.status === 404 ? "the API does not know this address yet; restart server.py" : ((await r.json().catch(() => null))?.error || `HTTP ${r.status}`)
      throw new Error(`The overview could not be loaded: ${why}.`)
    }).then(setData).catch((e) => setError(e.message))
  }, [])

  // the entries of the current family or use (one request per level)
  useEffect(() => {
    setEntries(null)
    if (level.kind !== "family" && level.kind !== "use") return
    let active = true
    const param = level.kind === "family" ? `family=${encodeURIComponent(levelValue)}` : `concept=${encodeURIComponent(levelValue)}`
    fetch(apiUrl(`/api/entries?identified=1&book=${book}&${param}&limit=50`)).then((r) => r.json())
      .then((x) => { if (active) setEntries(x.items || []) }).catch(() => { if (active) setEntries([]) })
    return () => { active = false }
  }, [level.kind, levelValue, book])

  const go = (l: Level) => setPath([...path, l])

  // nodes are built without the hover state, so hovering only restyles the edges (no flicker)
  const base = useMemo(() => {
    const nodes: Node[] = [], links: { id: string; source: string; target: string; n: number }[] = []
    if (!data) return { nodes, links }
    const bf = data.book_family.filter((r) => !book || r.book === book)
    const research = new Map(data.use_research.map((r) => [r.use, r.n]))
    const sum = (rows: Row[], key: string) => { const m = new Map<string, number>(); for (const r of rows) m.set(r[key], (m.get(r[key]) || 0) + r.n); return m }
    const familyNode = (f: string, n: number, x: number, y: number, maxN: number): Node => ({
      id: `f:${f}`, position: { x, y }, className: "ov-node ov-family", ...side, style: { width: 160 + 60 * (n / maxN) },
      data: { label: <div className="ov-label ov-family-label"><FamilyIcon family={f} className="ov-icon" /><span><strong>{f}</strong><small>{n} entries</small></span></div> },
    })
    const useNode = (u: string, n: number, x: number, y: number): Node => ({
      id: `u:${u}`, position: { x, y }, className: "ov-node ov-use", ...side,
      data: { label: <div className="ov-label"><strong>{u}</strong><small>{n} entries{research.get(u) ? ` · ${research.get(u)} claims with research` : ""}</small></div> },
    })
    const half = MAX_ENTRIES / 2
    const entryNode = (e: Row, i: number, x: number): Node => ({
      id: `e:${e.id}`, position: { x, y: (i % half) * 62 }, className: "ov-node ov-entry", ...side,
      data: { label: <div className="ov-label"><strong>{e.name || e.chapter}</strong><small>{e.preferred_scientific_name || ""}{e.book ? ` · ${BOOK_LABEL[e.book] || e.book}` : ""}</small></div> },
    })
    const centre = (id: string, label: string, sub: string, y: number, icon: boolean): Node => ({
      id, position: { x: 330, y }, className: "ov-node ov-centre", ...side,
      data: { label: <div className={`ov-label${icon ? " ov-family-label" : ""}`}>{icon && <FamilyIcon family={label} className="ov-icon" />}<span><strong>{label}</strong><small>{sub}</small></span></div> },
    })
    const count = entries ? ` (${entries.length}${entries.length >= 50 ? "+" : ""})` : ""

    if (level.kind === "all" || level.kind === "book") {
      const rows = level.kind === "book" ? bf.filter((r) => r.book === levelValue) : bf
      const famTotal = sum(rows, "family")
      const families = [...famTotal.entries()].sort((a, b) => b[1] - a[1]).slice(0, level.kind === "book" ? 20 : TOP_FAMILIES).map(([f]) => f)
      const maxF = Math.max(1, ...families.map((f) => famTotal.get(f) || 0))
      const books = [...new Set(rows.map((r) => r.book))]
      nodes.push(heading("h:1", 0, "Books"), heading("h:2", 330, "Plant families"))
      books.forEach((b, i) => nodes.push({
        id: `b:${b}`, position: { x: 0, y: 160 + i * 220 }, className: "ov-node ov-book", ...side,
        data: { label: <div className="ov-label"><strong>{BOOK_LABEL[b] || b}</strong><small>{rows.filter((r) => r.book === b).reduce((s, r) => s + r.n, 0)} plant links</small></div> },
      }))
      families.forEach((f, i) => nodes.push(familyNode(f, famTotal.get(f) || 0, 330, i * 64, maxF)))
      const famSet = new Set(families)
      rows.filter((r) => famSet.has(r.family)).forEach((r) => links.push({ id: `bf:${r.book}:${r.family}`, source: `b:${r.book}`, target: `f:${r.family}`, n: r.n }))
      if (level.kind === "all") {
        const fu = data.family_use.filter((r) => famSet.has(r.family))
        const useTotal = sum(fu, "use")
        const uses = [...useTotal.entries()].sort((a, b) => b[1] - a[1]).slice(0, TOP_USES).map(([u]) => u)
        const useSet = new Set(uses)
        nodes.push(heading("h:3", 720, "Medical uses (MeSH)"))
        uses.forEach((u, i) => nodes.push(useNode(u, useTotal.get(u) || 0, 720, i * 56)))
        fu.filter((r) => useSet.has(r.use)).sort((a, b) => b.n - a.n).slice(0, MAX_LINKS)
          .forEach((r) => links.push({ id: `fu:${r.family}:${r.use}`, source: `f:${r.family}`, target: `u:${r.use}`, n: r.n }))
      }
    } else if (level.kind === "family") {
      // a family and its plants (the historical entries whose proposed plant is in it), on both sides
      const list = (entries || []).slice(0, MAX_ENTRIES)
      const left = list.filter((_, i) => i % 2 === 0), right = list.filter((_, i) => i % 2 === 1)
      nodes.push(heading("h:1", 0, `Plants${count} · click one for its map`))
      nodes.push(centre(`f:${levelValue}`, levelValue, `plant family${entries ? ` · ${entries.length}${entries.length >= 50 ? "+" : ""} entries` : ""}`, Math.max(0, (Math.max(left.length, right.length) - 1) * 31), true))
      left.forEach((e, i) => { nodes.push(entryNode(e, i, 0)); links.push({ id: `ef:${e.id}`, source: `e:${e.id}`, target: `f:${levelValue}`, n: 1 }) })
      right.forEach((e, i) => { nodes.push(entryNode(e, i, 660)); links.push({ id: `fe:${e.id}`, source: `f:${levelValue}`, target: `e:${e.id}`, n: 1 }) })
    } else {
      const fams = data.family_use.filter((r) => r.use === levelValue).sort((a, b) => b.n - a.n).slice(0, 18)
      const maxF = Math.max(1, ...fams.map((r) => r.n))
      const list = (entries || []).slice(0, MAX_ENTRIES)
      nodes.push(heading("h:1", 0, "Plant families"), heading("h:3", 640, `Entries${count} · click one to open its map`))
      nodes.push(centre(`u:${levelValue}`, levelValue, `medical use${research.get(levelValue) ? ` · ${research.get(levelValue)} claims with research` : ""}`, Math.min(half, Math.max(list.length, fams.length)) * 28, false))
      fams.forEach((r, i) => { nodes.push(familyNode(r.family, r.n, 0, i * 64, maxF)); links.push({ id: `fu:${r.family}`, source: `f:${r.family}`, target: `u:${levelValue}`, n: r.n }) })
      list.forEach((e, i) => nodes.push(entryNode(e, i, i >= half ? 890 : 640)))
    }
    return { nodes, links }
  }, [data, book, level.kind, levelValue, entries])

  const edges: Edge[] = useMemo(() => {
    const maxN = Math.max(1, ...base.links.map((l) => l.n))
    const touches = (l: { source: string; target: string }) => !hover || l.source === hover || l.target === hover
    return base.links.map((l) => ({
      id: l.id, source: l.source, target: l.target,
      style: { strokeWidth: 1 + 7 * (l.n / maxN), stroke: touches(l) ? "var(--map-edge)" : "var(--map-edge-faint)", opacity: touches(l) ? 0.85 : 0.35 },
    }))
  }, [base.links, hover])

  if (error) return <p className="map-message" role="alert">{error}</p>
  if (!data) return <p className="map-message">Loading the overview…</p>
  return (
    <>
      <nav className="ov-crumbs" aria-label="Graph levels">
        {path.length > 0 && <button type="button" className="ov-back" onClick={() => setPath(path.slice(0, -1))}>‹ Back</button>}
        {[{ kind: "all" } as Level, ...path].map((l, i, all) => (
          <span key={i}>
            {i > 0 && <span className="ov-sep">›</span>}
            {i === all.length - 1
              ? <strong>{levelName(l)}</strong>
              : <button type="button" onClick={() => setPath(path.slice(0, i))}>{levelName(l)}</button>}
          </span>
        ))}
      </nav>
      <div className="knowledge-canvas ov-canvas">
        <ReactFlow key={`${level.kind}:${levelValue}:${book}:${entries ? "e" : ""}`} nodes={base.nodes} edges={edges} fitView fitViewOptions={{ padding: 0.08 }} minZoom={0.15} maxZoom={1.6}
          nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
          onNodeMouseEnter={(_, n) => setHover(n.id)} onNodeMouseLeave={() => setHover(null)}
          onNodeClick={(_, n) => {
            const [kind, ...rest] = n.id.split(":"), value = rest.join(":")
            setHover(null)
            if (kind === "b") go({ kind: "book", value })
            else if (kind === "f" && !(level.kind === "family" && levelValue === value)) go({ kind: "family", value })
            else if (kind === "u" && !(level.kind === "use" && levelValue === value)) go({ kind: "use", value })
            else if (kind === "e") onEntry(value)
          }}>
          <Background color="var(--map-grid)" gap={24} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="map-caption">
        {level.kind === "all" && <>The whole graph: each book is joined to the families of its proposed plants (A or B), and each family to the medical uses its entries record; thicker lines mean more entries. Click a book, family or use to go down a level.</>}
        {level.kind === "book" && <>The plant families proposed for this book's entries. Click a family to see its entries and uses.</>}
        {level.kind === "family" && <>The plants of this family: each box is a historical entry whose proposed plant (A or B) belongs to it, shown on both sides (up to {MAX_ENTRIES}). Click one to open its own, detailed map.</>}
        {level.kind === "use" && <>The plant families whose entries record this use (left) and the entries themselves (right, up to {MAX_ENTRIES}). Click a family to follow it, or an entry to open its own map.</>}
      </p>
    </>
  )
}
