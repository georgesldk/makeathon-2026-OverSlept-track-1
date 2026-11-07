import { useEffect, useMemo, useState } from 'react'
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react'
import { claimRef, tierLabel } from './display'
import { Dropdown } from './controls'

type Row = Record<string, any>
type Entry = { entry: Row; book: Row; names: Row[]; candidates: Row[]; claims: Row[]; historical_text?: string; introduction?: string; opening?: string }
type Kind = 'entry' | 'candidate' | 'claim' | 'mapping' | 'concept' | 'unit' | 'assessment' | 'study'
type Selection = { kind: Kind; id: string; label: string; data: Row }
const kindLabels: Record<Kind, string> = { entry: 'Historical entry', candidate: 'Plant hypothesis', claim: 'Historical claim', mapping: 'Concept mapping', concept: 'Medical concept', unit: 'Claim–plant unit', assessment: 'Evidence assessment', study: 'Modern study' }
const present = (v: unknown) => v === undefined || v === null || v === '' ? 'Not recorded' : Array.isArray(v) ? (v.length ? v.join(', ') : 'None recorded') : String(v)
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || 'Unable to load the knowledge map.')
  return data as T
}

export default function KnowledgeMap({ openEntry, initialEntryId = '' }: { openEntry: (id: string, target?: { tab: 'identification' | 'studies'; id: string; includeHidden?: boolean }) => void; initialEntryId?: string }) {
  const [search, setSearch] = useState('Carrots')
  const [term, setTerm] = useState('Carrots')
  const [book, setBook] = useState('')
  const [results, setResults] = useState<Row[]>([])
  const [moreResults, setMoreResults] = useState(false)
  const [entry, setEntry] = useState<Entry | null>(null)
  const [entryId, setEntryId] = useState(initialEntryId)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [focusClaim, setFocusClaim] = useState('')
  const [focusCandidate, setFocusCandidate] = useState('')
  const [candidateData, setCandidateData] = useState<Row | null>(null)
  const [claimData, setClaimData] = useState<Row | null>(null)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [visible, setVisible] = useState({ candidates: true, claims: true, concepts: true, studies: true, hidden: false })

  useEffect(() => { const timer = setTimeout(() => setTerm(search), 300); return () => clearTimeout(timer) }, [search])
  useEffect(() => {
    let active = true
    get<{items: Row[]; has_more: boolean}>(`/entries?identified=1&q=${encodeURIComponent(term)}&book=${book}&limit=20`)
      .then(result => { if (!active) return; setResults(result.items); setMoreResults(result.has_more); setError(''); if (!entryId && term === 'Carrots') { const example = result.items.find(x => x.name === 'Carrots' && x.book === 'culpeper'); if (example) setEntryId(example.id) } })
      .catch(e => { if (active) { setResults([]); setError(e.message) } })
    return () => { active = false }
  }, [term, book, entryId])
  useEffect(() => {
    if (!entryId) return
    let active = true
    setLoading(true); setError(''); setEntry(null); setSelection(null); setFocusClaim(''); setFocusCandidate(''); setClaimData(null); setCandidateData(null)
    get<Entry>(`/entries/${entryId}`).then(data => { if (active) { setEntry(data); setSelection({ kind: 'entry', id: data.entry.id, label: data.entry.name || data.entry.label, data: data.entry }) } }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [entryId])
  useEffect(() => {
    if (!focusClaim) { setClaimData(null); return }
    let active = true
    setClaimData(null); setDetailLoading(true); setDetailError('')
    get<Row>(`/claims/${focusClaim}`).then(data => { if (active) setClaimData(data) }).catch(e => { if (active) setDetailError(e.message) }).finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [focusClaim])
  useEffect(() => {
    if (selection?.kind !== 'candidate') { setCandidateData(null); return }
    let active = true
    setCandidateData(null); setDetailError('')
    get<Row>(`/candidates/${selection.id}`).then(data => { if (active) setCandidateData(data) }).catch(e => { if (active) setDetailError(e.message) })
    return () => { active = false }
  }, [selection?.kind, selection?.id])

  const selectClaim = (id: string) => {
    const item = entry?.claims.find(x => x.claim.id === id)
    setFocusClaim(id)
    if (item) { setVisible(v => ({...v, claims: true})); setSelection({ kind: 'claim', id, label: item.claim.claim_text, data: item.claim }) }
  }
  const selectCandidate = (id: string) => {
    const item = entry?.candidates.find(x => x.hypothesis.id === id)
    setFocusCandidate(id)
    if (item) { setVisible(v => ({...v, candidates: true})); setSelection({ kind: 'candidate', id, label: item.hypothesis.accepted_name || 'Unresolved candidate', data: item }) }
  }
  const candidates = useMemo(() => (entry?.candidates || []).filter(x => visible.hidden || ['A', 'B'].includes(x.decision?.tier)), [entry, visible.hidden])
  const graph = useMemo(() => {
    if (!entry) return { nodes: [] as Node[], edges: [] as Edge[] }
    const nodes: Node[] = []; const edges: Edge[] = []; const seen = new Set<string>()
    const add = (kind: Kind, id: string, label: string, data: Row, x: number, y: number, subtitle?: string) => {
      const key = `${kind}:${id}`; if (seen.has(key)) return key; seen.add(key)
      nodes.push({ id: key, position: { x, y }, className: `map-node map-node-${kind}`, data: { selection: { kind, id, label, data }, label: <><span className="map-node-type">{kindLabels[kind]}</span><strong>{label || 'Not recorded'}</strong>{subtitle && <small>{subtitle}</small>}</> } }); return key
    }
    const link = (source: string, target: string, label: string, dashed = false) => edges.push({ id: `${source}-${target}-${label}`, source, target, label, type: 'smoothstep', animated: false, style: { stroke: dashed ? '#ab815a' : '#82958a', strokeWidth: 1.5, strokeDasharray: dashed ? '5 5' : undefined }, labelStyle: { fill: '#596b60', fontSize: 10 }, labelBgStyle: { fill: '#f5f3eb', fillOpacity: .94 } })
    const root = add('entry', entry.entry.id, entry.entry.name || entry.entry.label, entry.entry, 0, 170, `${entry.entry.book === 'culpeper' ? 'Culpeper' : 'Dioscorides'} · ${entry.entry.label || ''}`)
    let cs = candidates.slice(0, 8)
    const focusedCandidate = candidates.find(x => x.hypothesis.id === focusCandidate)
    if (focusedCandidate && !cs.includes(focusedCandidate)) cs = [...cs.slice(0, 7), focusedCandidate]
    if (visible.candidates) cs.forEach((x, i) => { const h = x.hypothesis; const id = add('candidate', h.id, h.accepted_name || 'Unresolved candidate', x, 300, i * 125, `${tierLabel(x.decision?.tier)} · ${present(h.rank)}`); link(root, id, 'proposed', true) })
    let claims = entry.claims.slice(0, 8)
    const focused = entry.claims.find(x => x.claim.id === focusClaim)
    if (focused && !claims.includes(focused)) claims = [...claims.slice(0, 7), focused]
    const claimStart = visible.candidates ? Math.max(cs.length * 125 + 60, 250) : 0
    if (visible.claims) claims.forEach((item, i) => {
      const c = item.claim; const y = claimStart + i * 130
      const id = add('claim', c.id, c.claim_text || 'Historical claim', c, 300, y, c.source_claim_id?.split(':').pop()); link(root, id, 'records')
      if (visible.concepts) item.concepts.slice(0, 4).forEach((m: Row, j: number) => {
        const mapping = add('mapping', m.mapping_id, `${present(m.match)} mapping`, m, 650, y + j * 100, present(m.proposed))
        const concept = add('concept', m.node_id, m.name, m, 970, y + j * 100, `MeSH · ${present(m.id)}`)
        link(id, mapping, 'has mapping'); link(mapping, concept, 'maps to')
      })
    })
    if (visible.claims && visible.studies && focused && claimData) {
      const ckey = `claim:${focused.claim.id}`; let studyIndex = 0
      claimData.studies.slice(0, 6).forEach((row: Row) => {
        if (!row.unit?.id || !row.assessment?.id || !row.study?.id) return
        const y = claimStart + studyIndex++ * 135
        const unit = add('unit', row.unit.id, row.candidate || row.unit.taxon_name || 'Claim–plant unit', row.unit, 650, y, 'Recorded claim–plant combination')
        const assessment = add('assessment', row.assessment.id, row.assessment.relevance || row.assessment.verdict || 'Evidence assessment', { ...row.assessment, excerpts: row.excerpts }, 970, y, 'Assessment of this study')
        const study = add('study', row.study.id, row.study.title || 'Untitled study', { ...row.study, source_url: row.source_url }, 1290, y, 'Modern research')
        link(unit, ckey, 'about claim'); link(assessment, unit, 'assesses unit'); link(assessment, study, 'assesses study')
      })
    }
    return { nodes, edges: Array.from(new Map(edges.map(edge => [edge.id, edge])).values()) }
  }, [entry, candidates, focusCandidate, focusClaim, claimData, visible])
  const toggle = (key: keyof typeof visible) => setVisible(v => ({...v, [key]: !v[key]}))
  return <main className="knowledge-page">
    <header className="knowledge-hero"><div><p className="eyebrow">Explore the connections</p><h1>Historical knowledge map<span>.</span></h1><p>Follow the evidence from a historical passage to botanical hypotheses, medicinal concepts and modern research.</p></div><div className="knowledge-hero-mark" aria-hidden="true"><span>✳</span><small>ETHNOTRACE<br/>KNOWLEDGE GRAPH</small></div></header>
    <div className="knowledge-notice"><span>✳</span><p><strong>Explore, don't assume.</strong> Botanical identifications are hypotheses; historical claims and linked studies do not prove a treatment works.</p></div>
    <div className="knowledge-layout">
      <aside className="knowledge-sidebar" aria-label="Map controls">
        <div className="map-sidebar-heading"><span>01 / START HERE</span><h2>Choose a record</h2><p>Search by historical or scientific name, then select an entry.</p></div>
        <label className="map-field">Search the collection<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Try Carrots or μῆον" /></label>
        <div className="map-field">Historical source<Dropdown label="Historical source" value={book} onChange={setBook} options={[{ value: '', label: 'All entries' }, { value: 'culpeper', label: 'Culpeper', hint: 'The Complete Herbal, 1653' }, { value: 'dioscorides', label: 'Dioscorides', hint: 'De materia medica, 1st century' }]} /></div>
        <div className="map-results" aria-label="Matching historical entries">{results.map(r => <button key={r.id} className={entryId === r.id ? 'active' : ''} onClick={() => setEntryId(r.id)}><strong>{r.name || r.chapter}</strong><small>{r.book === 'culpeper' ? 'Culpeper' : 'Dioscorides'} · {r.chapter || 'Historical entry'}</small></button>)}{moreResults && <p>Showing the first 20 matches. Refine your search to see more.</p>}{!results.length && !error && <p>No matching entries. Try another name.</p>}</div>
        <div className="map-sidebar-heading map-layer-heading"><span>02 / SHAPE THE MAP</span><h2>Visible layers</h2><p>Choose what to display around the selected entry.</p></div>
        <div className="map-layer-list switch-list">{([['candidates','Plant hypotheses'],['claims','Historical claims'],['concepts','Medical concepts'],['studies','Research connections'],['hidden','Include excluded candidates']] as [keyof typeof visible, string][]).map(([key,label]) => <label key={key}><input type="checkbox" checked={visible[key]} onChange={() => toggle(key)}/><span className={`map-legend-dot map-dot-${key}`}/>{label}</label>)}</div>
        {entry && <><div className="map-field">Focus a candidate<Dropdown label="Focus a candidate" value={focusCandidate} placeholder="Choose a candidate" onChange={v => v && selectCandidate(v)} options={candidates.map(x => ({ value: x.hypothesis.id, label: x.hypothesis.accepted_name || 'Unresolved', hint: tierLabel(x.decision?.tier) }))} /></div><div className="map-field">Explore research for a claim<Dropdown label="Explore research for a claim" value={focusClaim} placeholder="Choose a claim" onChange={v => v && selectClaim(v)} options={entry.claims.map(x => ({ value: x.claim.id, label: x.claim.claim_text }))} /></div></>}
      </aside>
      <section className="knowledge-workspace" aria-label="Interactive knowledge map">
        <div className="map-workspace-head"><div><span className="map-overline">THE EVIDENCE LANDSCAPE</span><h2>{entry ? entry.entry.name || entry.entry.label : 'Your map begins here'}</h2><p>{entry ? `${entry.entry.book === 'culpeper' ? 'Culpeper' : 'Dioscorides'} · ${entry.entry.label || 'Historical entry'}` : 'Select an entry to explore its connections.'}</p></div><div className="map-workspace-count"><strong>{graph.nodes.length}</strong><span>visible nodes</span></div></div>
        {error && <p className="map-message" role="alert">{error}</p>}{loading && <p className="map-message">Loading the historical record…</p>}
        {entry && <><div className="knowledge-canvas"><ReactFlow key={entry.entry.id} nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.08} maxZoom={1.8} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => { const s = node.data.selection as Selection; setSelection(s); if (s.kind === 'claim') setFocusClaim(s.id); if (s.kind === 'candidate') setFocusCandidate(s.id) }}><Background color="#d5ddd2" gap={24} size={1}/><Controls showInteractive={false}/><MiniMap pannable zoomable nodeColor={n => n.className?.includes('claim') ? '#b8905b' : n.className?.includes('study') ? '#8c83a7' : '#6e967a'} maskColor="rgba(232,237,227,.7)"/></ReactFlow><div className="map-canvas-hint">DRAG TO EXPLORE · SCROLL TO ZOOM · SELECT A NODE</div></div><div className="map-caption">Showing up to 8 candidates and 8 claims, with up to 4 mappings per claim; use the selectors to focus any other record. Select a claim to load up to 6 study connections. For complete lists, open the full record.</div></>}
        {!entry && !loading && <div className="map-placeholder"><span>✳</span><p>Choose a historical entry to reveal its connections.</p></div>}
        <div className="map-inspector" aria-live="polite"><div className="map-inspector-heading"><div><span className="map-overline">03 / INSPECT THE EVIDENCE</span><h3>{selection ? kindLabels[selection.kind] : 'Select a node'}</h3></div><span>↗</span></div>
          {selection ? <><h4>{selection.label}</h4>{selection.kind === 'entry' && <><p>{entry?.historical_text || entry?.introduction || entry?.opening || 'No historical passage recorded.'}</p><button className="map-link" onClick={() => openEntry(selection.id)}>Open full historical record →</button></>}
          {selection.kind === 'candidate' && <><p>{tierLabel(selection.data.decision?.tier)} · {present(selection.data.hypothesis?.rank)}. This is a proposed historical identification.</p>{candidateData && <><span className="map-detail-label">Supporting evidence · showing {Math.min(4, candidateData.evidence.length)} of {candidateData.evidence.length} returned</span>{candidateData.evidence.slice(0, 4).map((v: Row, i: number) => <div className="map-evidence" key={v.id || i}><strong>{present(v.source)} · {present(v.grade)}</strong><p>{present(v.source_record_id)}{v.lexicon_citations?.length ? ` · ${present(v.lexicon_citations)}` : ''}</p>{v.quote && <p>“{v.quote}”</p>}</div>)}{!candidateData.evidence.length && <p>No linked evidence records returned.</p>}<button className="map-link" onClick={() => openEntry(entry!.entry.id, {tab: 'identification', id: selection.id, includeHidden: selection.data.decision?.tier === 'X'})}>Open full record for all evidence →</button></>}</>}
          {selection.kind === 'claim' && <><span className="map-detail-label">Original quotation</span><blockquote>“{present(selection.data.quote)}”</blockquote><p>Source: {claimRef(selection.data.source_claim_id, entry?.entry?.name)}</p>{detailLoading && <p>Loading connected research…</p>}{claimData && <p>{claimData.studies.length} study connections returned on the first page{claimData.has_more ? ' · more in the full record' : ''}.</p>}<button className="map-link" onClick={() => openEntry(entry!.entry.id, {tab: 'studies', id: selection.id})}>Open claim in full record →</button></>}
          {selection.kind === 'mapping' && <><p>Mapping: {present(selection.data.match)} · Proposed term: {present(selection.data.proposed)} · Via: {present(selection.data.via)}</p><p>This mapping describes recorded terminology; it does not establish treatment effectiveness.</p></>}
          {selection.kind === 'concept' && <p>MeSH ID: {present(selection.data.id)}</p>}
          {selection.kind === 'unit' && <p>This node represents the recorded claim–plant combination assessed in the connected research.</p>}
          {selection.kind === 'assessment' && <><p>Assessment: {present(selection.data.relevance || selection.data.verdict)}</p>{(selection.data.excerpts || []).filter((x: Row) => x.text).map((x: Row, i: number) => <blockquote key={i}>{x.text}</blockquote>)}<button className="map-link" onClick={() => openEntry(entry!.entry.id, {tab: 'studies', id: focusClaim})}>Inspect assessments in full record →</button></>}
          {selection.kind === 'study' && <><p>{present(selection.data.title)}</p>{selection.data.source_url?.startsWith('https://') && <a className="map-link" href={selection.data.source_url} target="_blank" rel="noreferrer">Open study source ↗</a>}<button className="map-link" onClick={() => openEntry(entry!.entry.id, {tab: 'studies', id: focusClaim})}>Inspect research in full record →</button></>}
          {detailError && <p role="alert">{detailError}</p>}</> : <p>Choose a node to view its source and context.</p>}</div>
        {entry && <details className="map-accessible-list"><summary>Browse visible nodes as a list</summary>{graph.nodes.map(n => { const s = n.data.selection as Selection; return <button key={n.id} onClick={() => { setSelection(s); if (s.kind === 'claim') selectClaim(s.id); if (s.kind === 'candidate') selectCandidate(s.id) }}>{kindLabels[s.kind]} · {s.label}</button> })}</details>}
      </section>
    </div>
  </main>
}
