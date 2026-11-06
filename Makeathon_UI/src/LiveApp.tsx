import { useEffect, useId, useMemo, useState } from "react"
import {
  ReactFlow,
  Background,
  Controls,
  useEdgesState,
  useNodesState,
  type Node,
  type Edge,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import KnowledgeMap from "./KnowledgeMap"
import PlantDashboard from "./PlantDashboard"
import { friendly, tierLabel } from "./display"

type Item = Record<string, any>
type Tab = "overview" | "history" | "identification" | "uses" | "studies" | "relationships"
type Entry = {
  entry: Item
  book: Item
  names: Item[]
  candidates: Item[]
  claims: Item[]
  historical_text?: string
  introduction?: string
  opening?: string
  page?: string
  description?: string
  place?: string
  season?: string
  virtues?: string
  image?: Item | null
  preferred_scientific_name?: string | null
}
const bookName = (book: string) =>
  book === "culpeper" ? "Culpeper" : "Dioscorides"
const sourceUrl = (id: unknown) =>
  typeof id === "string" && /^gbif:[0-9]+$/.test(id)
    ? `https://www.gbif.org/species/${id.slice(5)}`
    : undefined
const safeHttps = (url: unknown) =>
  typeof url === "string" && url.startsWith("https://") ? url : undefined
const value = (v: unknown) =>
  v === null || v === undefined || v === ""
    ? "Not recorded"
    : typeof v === "boolean"
      ? v ? "Yes" : "No"
    : Array.isArray(v)
      ? v.length
        ? v.join(", ")
        : "None recorded"
      : String(v)
const tierText = tierLabel
const tierClass = (tier?: string) =>
  tier === "A" ? "shown" : tier === "B" ? "possible" : "contested"
async function api<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`)
  } catch {
    throw new Error(
      "The local research API is not reachable. Check that it is running.",
    )
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok)
    throw new Error(body.error || `Request failed (${response.status})`)
  return body as T
}
const tierHelp: Record<string, string> = {
  A: "This candidate passed the recorded eligibility rules. It is still a hypothesis, not a proven historical identification.",
  B: "The candidate is considered possible, but the recorded evidence has limitations or unresolved questions.",
  X: "The candidate is hidden by the eligibility rules. It remains available for inspection and is not deleted.",
}
const tabHelp: Record<string, string> = {
  overview: "A summary of this historical entry and ways to explore it.",
  history: "The historical text and the names recorded for this entry.",
  identification:
    "Candidate modern identifications, eligibility rules, and supporting evidence.",
  uses: "Extracted historical claims, medical concept mappings, and connected research.",
  relationships: "A focused graph of the entry and its recorded relationships.",
}
const termHelp: Record<string, string> = {
  Family:
    "A botanical family groups related plants. This is the family recorded for the candidate by the pipeline.",
  Rank: "The taxonomic level of the candidate, such as species, genus, or family.",
  "Selected by":
    "The taxonomic source used by the pipeline when selecting this candidate's accepted name.",
  Rules:
    "The identifiers of the eligibility rules applied by the pipeline to this candidate.",
  Reasons:
    "Recorded reasons why the candidate was hidden or could not be classified.",
  Caveats:
    "Recorded uncertainties or limitations that accompany the candidate's classification.",
  Geography:
    "The pipeline's recorded comparison with the historical region. Modern distribution alone does not establish historical presence.",
  "Counted strong lineages":
    "Source lineages the pipeline counted as strong support. Multiple records from one lineage are not necessarily independent.",
  "Passage-specific":
    "Whether the pipeline recorded evidence as referring to this historical passage. The citation still requires source review.",
  "Plant part":
    "The plant part recorded for the historical claim; missing or unknown parts have not been inferred.",
  Preparation:
    "How the historical source describes preparing the remedy, when recorded.",
  Route:
    "How the remedy was administered, when recorded in the extracted claim.",
  "Extraction flags":
    "Warnings recorded when the historical claim was extracted; they are not an independent review.",
  "Unmapped terms":
    "Historical terms for which the pipeline did not record a MeSH mapping.",
  "Evidence type":
    "The type of study recorded by the assessment, such as a systematic review or laboratory study.",
  Relevance:
    "How the recorded assessment relates the study to the historical claim.",
  Finding:
    "The recorded direction of the study's finding. A positive result alone does not prove clinical effectiveness.",
  Applicability:
    "How closely the study matches the particular historical claim and plant, according to the recorded assessment.",
  Compatibility:
    "How the assessment compares the study with the historical species, condition, plant part, and route.",
  Review:
    "Whether the recorded assessment has been reviewed. A model-generated assessment may remain unreviewed.",
  MeSH: "Medical Subject Headings are a vocabulary used to map medical concepts. An approximate mapping does not make the terms identical.",
  "Original name": "The scientific name sent to the taxonomic resolution step, as recorded in the source data.",
  "Accepted name": "The name returned by this authority for this resolution. Acceptance does not prove the historical identification.",
  "Resolution rule": "The rule the pipeline recorded when resolving the original scientific name.",
  "Authority ID": "The accepted taxon identifier supplied by the named taxonomic authority.",
  "Authority release": "The authority release recorded by the pipeline for this taxonomic assertion.",
  "Matched text": "The source text recorded as matching the historical name; a match alone does not prove the plant's identity.",
  "Source candidate": "The scientific name recorded by this source before subsequent taxonomic reconciliation.",
  "Source name with authorship": "The full scientific name recorded by the source, including authorship when supplied.",
  "Match type": "How the pipeline classified the match between the source name and the historical name.",
  "Source lineage": "The source family assigned by the pipeline for assessing whether evidence records are independent.",
  "Source record": "The original source record identifier retained by the pipeline.",
  "Evidence grade": "The pipeline's recorded grade for this evidence row. Strong support is not proof of historical identity.",
  "Lexicon entry": "The entry identifier recorded for this lexicon source.",
  "Recorded citations": "The chapter citations recorded by the pipeline for this lexicon evidence; they still require source review.",
  "Evidence link": "Whether the pipeline linked this evidence record to one candidate, or left it unmatched or ambiguous.",
}

function InfoTip({ label, text }: { label: string; text: string }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  return (
    <span
      className="info-tip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="info-trigger"
        aria-label={`About ${label}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          setOpen(true)
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false)
        }}
      >
        i
      </button>
      {open && (
        <span className="info-popover" role="tooltip" id={id}>
          {text}
        </span>
      )}
    </span>
  )
}
function Status({ tier }: { tier?: string }) {
  return (
    <span
      className={`status ${tierClass(tier)}`}
      title={
        tierHelp[tier || ""] ||
        "No eligibility decision is linked to this candidate."
      }
    >
      {tierText(tier)}
    </span>
  )
}
function Notice({ children }: { children: React.ReactNode }) {
  return <div className="notice">{children}</div>
}
function Facts({ values }: { values: [string, unknown][] }) {
  return (
    <dl className="record-facts">
      {values.map(([k, v]) => (
        <div key={k}>
          <dt>
            {k}
            {termHelp[k] && <InfoTip label={k} text={termHelp[k]} />}
          </dt>
          <dd>{value(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

const ruleHelp: Record<string, string> = {
  A1: "The pipeline found an accepted name in a plant list.",
  A2: "The recorded taxonomic rank is species level or below.",
  A3: "The recorded name is settled without a WFO–WCVP disagreement.",
  A4a: "The decision counted strong support from at least two source lineages.",
  A4b: "The decision counted passage-specific support with additional corroboration.",
  A5: "The recorded geographical assessment passed the pipeline's historical compatibility rule.",
  A6: "The recorded botanical description comparison met the eligibility threshold.",
  "A6 n/a": "The pipeline recorded no historical description to compare under this rule.",
  B1: "The candidate has limited support from a single lineage.",
  B2: "The taxonomic authorities disagree on the accepted name.",
  B3: "The recorded geographical evidence is uncertain.",
  B4: "The name was settled only through Global Names rather than the main plant lists.",
  B5: "The candidate is supported only by an uncorroborated scholarly identification.",
  B6: "The recorded botanical description comparison has a weak or poor fit.",
  B7: "The candidate was not assessed against the historical description or lacked comparable data.",
  B9: "Geography was not checked for this candidate.",
  X1: "Only weak name evidence was recorded.",
  X2: "The recorded geographical assessment did not fit the historical context.",
  X3: "The candidate was not tied to an accepted name.",
  X4: "The candidate was classified as non-plant under the recorded rule.",
  X5: "The candidate was reached only through a name not used by the book for this entry.",
  X6: "The candidate is at genus or family level rather than a confirmed species-level name.",
  X7: "Plant status was not established by the recorded sources.",
  X8: "The taxonomic rank was not established.",
}

function FactTile({ label, content }: { label: string; content: unknown }) {
  return (
    <div className="classification-fact">
      <dt>{label}{termHelp[label] && <InfoTip label={label} text={termHelp[label]} />}</dt>
      <dd>{Array.isArray(content) && content.length > 0 ? <ul className="classification-notes">{content.map((item, index) => <li key={index}>{String(item)}</li>)}</ul> : value(content)}</dd>
    </div>
  )
}

function ClassificationSummary({ hypothesis, decision }: { hypothesis: Item; decision: Item | null }) {
  const rules = Array.isArray(decision?.rules) ? decision.rules : null
  const lineages = Array.isArray(decision?.lineages_strong) ? decision.lineages_strong : null
  return (
    <section className="classification-panel" aria-label="Classification and geography">
      <div className="classification-block">
        <p className="classification-kicker">Botanical classification</p>
        <dl className="classification-facts classification-facts-three">
          <FactTile label="Family" content={hypothesis.family} />
          <FactTile label="Rank" content={hypothesis.rank} />
          <FactTile label="Selected by" content={hypothesis.decided_by} />
        </dl>
      </div>
      <div className="classification-block">
        <p className="classification-kicker">Eligibility decision</p>
        <div className="classification-label">Why this identification was classified this way <InfoTip label="Identification criteria" text="These are the recorded pipeline criteria; they are not independent verification of historical identity." /></div>
        {rules?.length ? <ul className="classification-notes classification-rule-explanations">{rules.map((rule: string, i: number) => <li key={`${rule}-${i}`}>{ruleHelp[rule] || "A classification criterion was recorded; consult the source data for details."}</li>)}</ul> : <p className="classification-empty">{rules ? "None recorded" : "Not recorded"}</p>}
        <dl className="classification-facts classification-facts-two">
          <FactTile label="Reasons" content={decision?.reasons} />
          <FactTile label="Caveats" content={decision?.caveats} />
        </dl>
      </div>
      <div className="classification-block">
        <p className="classification-kicker">Historical context</p>
        <dl className="classification-facts classification-facts-two">
          <FactTile label="Geography" content={decision?.geography} />
          <FactTile label="Passage-specific" content={decision?.passage_specific} />
        </dl>
        <div className="lineages-heading">Counted strong lineages <InfoTip label="Counted strong lineages" text={termHelp["Counted strong lineages"]} /></div>
        {lineages?.length ? <details className="lineage-list"><summary>{lineages.length} {lineages.length === 1 ? "lineage" : "lineages"} counted by the pipeline</summary><ul>{lineages.map((lineage: string, i: number) => <li key={`${lineage}-${i}`}>{lineage}</li>)}</ul></details> : <p className="classification-empty">{lineages ? "None recorded" : "Not recorded"}</p>}
      </div>
    </section>
  )
}

function ClaimSummary({ claim, concepts }: { claim: Item; concepts: Item[] }) {
  return (
    <section className="classification-panel claim-summary" aria-label="Historical claim details">
      <div className="classification-block">
        <p className="classification-kicker">Extracted interpretation</p>
        <p className="claim-interpretation">{value(claim.claim_text)}</p>
      </div>
      <div className="classification-block">
        <p className="classification-kicker">Historical preparation</p>
        <dl className="classification-facts classification-facts-three">
          <FactTile label="Plant part" content={claim.plant_part} />
          <FactTile label="Preparation" content={claim.preparation} />
          <FactTile label="Route" content={claim.route} />
        </dl>
      </div>
      <div className="classification-block">
        <p className="classification-kicker">Medical concept mapping <InfoTip label="MeSH" text={termHelp.MeSH} /></p>
        {concepts.length ? (
          <div className="concept-list">
            {concepts.map((concept, index) => (
              <div className="concept-item" key={`${concept.id}-${index}`}>
                <div className="concept-title"><strong>{value(concept.name)}</strong><span className="concept-match">{friendly(concept.match)}</span></div>
                <dl className="classification-facts classification-facts-three concept-facts">
                  <FactTile label="MeSH ID" content={concept.id} />
                  <FactTile label="Proposed term" content={concept.proposed} />
                  <FactTile label="Via" content={concept.via} />
                </dl>
              </div>
            ))}
          </div>
        ) : <p className="classification-empty">No mapping recorded</p>}
      </div>
      <div className="classification-block">
        <p className="classification-kicker">Extraction notes</p>
        <dl className="classification-facts classification-facts-two">
          <FactTile label="Extraction flags" content={claim.flags} />
          <FactTile label="Unmapped terms" content={claim.mesh_not_found} />
        </dl>
      </div>
    </section>
  )
}

function TaxonomicResolutionCard({ resolution }: { resolution: Item }) {
  return (
    <article className="source-detail-card resolution-card">
      <header className="source-detail-header">
        <div><span className="classification-kicker">Taxonomic authority</span><h4>{value(resolution.authority)}</h4></div>
        {resolution.agreement === "disagree" && <span className="source-warning">Authorities disagree</span>}
      </header>
      <dl className="classification-facts classification-facts-two source-detail-facts">
        <FactTile label="Original name" content={resolution.original_name} />
        <FactTile label="Accepted name" content={resolution.accepted_name} />
        <FactTile label="Resolution rule" content={resolution.rule} />
        <FactTile label="Authority ID" content={resolution.source_id} />
        <FactTile label="Authority release" content={resolution.release} />
      </dl>
      {(resolution.wfo_reason || resolution.wcvp_reason || resolution.global_names_reason) && (
        <div className="source-detail-notes">
          <p className="classification-kicker">Recorded resolution notes</p>
          {resolution.wfo_reason && <p>WFO: {resolution.wfo_reason}</p>}
          {resolution.wcvp_reason && <p>WCVP: {resolution.wcvp_reason}</p>}
          {resolution.global_names_reason && <p>Global Names: {resolution.global_names_reason}</p>}
        </div>
      )}
    </article>
  )
}

function EvidenceCard({ evidence, showLinkStatus = false }: { evidence: Item; showLinkStatus?: boolean }) {
  const e = evidence
  const sourceNames: Record<string, string> = { checklistbank: "ChecklistBank", gbif: "GBIF", wikidata: "Wikidata", inaturalist: "iNaturalist", drduke: "Dr. Duke’s", taxtree: "TaxTree", lexicon: "Lexicon" }
  return (
    <article className="source-detail-card evidence-card">
      <header className="source-detail-header">
        <div><span className="classification-kicker">Evidence source</span><h4>{e.lexicon ? `${e.lexicon} · ${sourceNames[e.source] || value(e.source)}` : sourceNames[e.source] || value(e.source)}</h4></div>
        <div className="evidence-grade"><span className="status">{e.grade ? `${e.grade} evidence` : "Grade not recorded"}</span><InfoTip label="Evidence grade" text={termHelp["Evidence grade"]} /></div>
      </header>
      <dl className="classification-facts classification-facts-two source-detail-facts">
        <FactTile label="Matched text" content={e.matched_text} />
        <FactTile label="Source candidate" content={e.original_candidate} />
        {e.candidate_full && e.candidate_full !== e.original_candidate && <FactTile label="Source name with authorship" content={e.candidate_full} />}
        <FactTile label="Match type" content={e.match_type} />
        <FactTile label="Source lineage" content={e.source_lineage} />
        <FactTile label="Source record" content={e.source_record_id} />
        {showLinkStatus && <FactTile label="Evidence link" content={e.hypothesis_link_status} />}
        {e.lexicon && <FactTile label="Lexicon entry" content={e.lexicon_entry} />}
        {e.lexicon && <FactTile label="Recorded citations" content={e.lexicon_citations} />}
        {e.lexicon && <FactTile label="Evidence bridge" content={e.bridge} />}
      </dl>
      {sourceUrl(e.source_record_id) && <a className="source-record-link" href={sourceUrl(e.source_record_id)} target="_blank" rel="noreferrer">Open source record ↗</a>}
    </article>
  )
}

function AssessmentFacts({ values }: { values: [string, unknown][] }) {
  return (
    <dl className="assessment-facts">
      {values.map(([label, content]) => (
        <div key={label}>
          <dt>
            {label}
            {termHelp[label] && (
              <InfoTip label={label} text={termHelp[label]} />
            )}
          </dt>
          <dd>{friendly(content)}</dd>
        </div>
      ))}
    </dl>
  )
}

function EntryEvidence({ id }: { id: string }) {
  const [opened, setOpened] = useState(false),
    [offset, setOffset] = useState(0)
  const [data, setData] = useState<Item | null>(null),
    [error, setError] = useState("")
  useEffect(() => {
    if (!opened) return
    let active = true
    setError("")
    setData(null)
    api<Item>(`/entries/${id}/evidence?offset=${offset}`)
      .then((x) => {
        if (active) setData(x)
      })
      .catch((e) => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
    }
  }, [id, offset, opened])
  return (
    <details
      className="live-section"
      onToggle={(e) => setOpened(e.currentTarget.open)}
    >
      <summary>All entry evidence, including unlinked records</summary>
      <p>
        Unmatched or ambiguous records remain on the historical entry; they are
        not automatically assigned to a candidate.
      </p>
      {error && <p role="alert">{error}</p>}
      {opened && !data && !error && <p>Loading evidence…</p>}
      {data && (
        <>
          <div className="source-detail-list">{data.items.map((v: Item) => <EvidenceCard key={v.id} evidence={v} showLinkStatus />)}</div>
          <div className="pagination">
            <button
              className="secondary-button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Previous
            </button>
            <button
              className="secondary-button"
              disabled={!data.has_more}
              onClick={() => setOffset(offset + 20)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </details>
  )
}

function Graph({
  record,
  visible,
  openCandidate,
  openClaim,
}: {
  record: Entry
  visible: Item[]
  openCandidate: (id: string) => void
  openClaim: (id: string) => void
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [info, setInfo] = useState<Item | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState("")
  const candidates = visible.slice(0, 8)
  const claims = record.claims.slice(0, 8)
  useEffect(() => {
    const ns: Node[] = [
      {
        id: "book",
        position: { x: 0, y: 0 },
        data: {
          label: bookName(record.entry.book),
          kind: "Historical source",
          text: record.book.source,
        },
        className: "flow-historical",
      },
      {
        id: "entry",
        position: { x: 250, y: 0 },
        data: {
          label: record.entry.name || record.entry.label,
          kind: "Historical entry",
          text: record.entry.label || record.entry.entry_key,
        },
        className: "flow-historical",
      },
    ]
    const es: Edge[] = [
      { id: "book-entry", source: "entry", target: "book", label: "in book" },
    ]
    candidates.forEach((row, i) => {
      const h = row.hypothesis,
        d = row.decision
      ns.push({
        id: `h:${h.id}`,
        position: { x: 540, y: i * 92 },
        data: {
          label: h.accepted_name || "Unresolved candidate",
          kind: "Proposed identification",
          text: `${tierText(d?.tier)} · ${value(h.rank)}`,
          ref: h.id,
        },
        className: "flow-candidate",
      })
      es.push({
        id: `entry-${h.id}`,
        source: "entry",
        target: `h:${h.id}`,
        label: "proposed",
        style: { strokeDasharray: "5 4" },
      })
      if (d?.id) {
        ns.push({
          id: `d:${d.id}`,
          position: { x: 810, y: i * 92 },
          data: {
            label: tierText(d.tier),
            kind: "Eligibility decision",
            text: `Criteria: ${Array.isArray(d.rules) ? d.rules.map((rule: string) => ruleHelp[rule] || "Recorded classification criterion").join(" ") : "Not recorded"} · Caveats: ${value(d.caveats)}`,
          },
          className: "flow-claim",
        })
        es.push({
          id: `decision-${d.id}`,
          source: `h:${h.id}`,
          target: `d:${d.id}`,
          label: "decision",
        })
      }
    })
    claims.forEach((row, i) => {
      const c = row.claim
      ns.push({
        id: `c:${c.id}`,
        position: {
          x: (i % 4) * 255,
          y:
            Math.max(210, candidates.length * 92 + 80) +
            Math.floor(i / 4) * 110,
        },
        data: {
          label: c.claim_text || "Historical claim",
          kind: "Extracted historical claim",
          text: c.quote,
          ref: c.id,
        },
        className: "flow-claim",
      })
      es.push({
        id: `entry-${c.id}`,
        source: "entry",
        target: `c:${c.id}`,
        label: "claim",
      })
    })
    setNodes(ns)
    setEdges(es)
    setInfo(null)
  }, [record, visible, setNodes, setEdges])
  const expand = async () => {
    if (!info?.ref || !info.position) return
    setGraphLoading(true)
    setGraphError("")
    try {
      const added: Node[] = []
      const links: Edge[] = []
      const x = Math.max(...nodes.map((n) => n.position.x), 0) + 300,
        y = info.position.y
      if (info.kind === "Proposed identification") {
        const data = await api<Item>(`/candidates/${info.ref}`)
        data.resolutions
          .filter((r: Item) => r.resolution_id)
          .slice(0, 4)
          .forEach((r: Item, i: number) => {
            added.push({
              id: `r:${r.resolution_id}`,
              position: { x, y: y + i * 110 },
              data: {
                label: r.original_name,
                kind: "Taxonomic resolution",
                text: `${value(r.agreement)} · ${value(r.authority)} ${value(r.rule)}`,
              },
              className: "flow-candidate",
            })
            links.push({
              id: `hr:${info.ref}:${r.resolution_id}`,
              source: `h:${info.ref}`,
              target: `r:${r.resolution_id}`,
              label: "name resolution",
            })
            if (r.taxon_id) {
              added.push({
                id: `t:${r.taxon_id}`,
                position: { x: x + 260, y: y + i * 110 },
                data: {
                  label: r.accepted_name || r.source_id,
                  kind: "Authority taxon record",
                  text: `${r.authority} · ${r.source_id} · ${r.release}`,
                },
                className: "flow-candidate",
              })
              links.push({
                id: `rt:${r.resolution_id}:${r.taxon_id}`,
                source: `r:${r.resolution_id}`,
                target: `t:${r.taxon_id}`,
                label: `${r.authority}: ${r.rule}`,
              })
            }
          })
        data.evidence.slice(0, 5).forEach((e: Item, i: number) => {
          added.push({
            id: `v:${e.id}`,
            position: { x: x + 550, y: y + i * 110 },
            data: {
              label: `${e.source} · ${e.grade}`,
              kind: "Evidence record",
              text: `${value(e.original_candidate)} · ${value(e.source_record_id)} · ${value(e.lexicon_citations)}`,
            },
            className: "flow-claim",
          })
          links.push({
            id: `vh:${e.id}`,
            source: `v:${e.id}`,
            target: `h:${info.ref}`,
            label: "relates to",
          })
        })
      } else {
        const data = await api<Item>(`/claims/${info.ref}`)
        const row = record.claims.find((c) => c.claim.id === info.ref)
        row?.concepts.slice(0, 4).forEach((c: Item, i: number) => {
          added.push(
            {
              id: `m:${c.mapping_id}`,
              position: { x, y: y + i * 110 },
              data: {
                label: `${value(c.match)} mapping`,
                kind: "Medical concept mapping",
                text: value(c.proposed),
              },
              className: "flow-claim",
            },
            {
              id: `mesh:${c.node_id}`,
              position: { x: x + 250, y: y + i * 110 },
              data: { label: c.name, kind: "MeSH concept", text: c.id },
              className: "flow-candidate",
            },
          )
          links.push(
            {
              id: `cm:${c.mapping_id}`,
              source: `c:${info.ref}`,
              target: `m:${c.mapping_id}`,
              label: "mapping",
            },
            {
              id: `mt:${c.mapping_id}`,
              source: `m:${c.mapping_id}`,
              target: `mesh:${c.node_id}`,
              label: "maps to",
            },
          )
        })
        data.studies.slice(0, 4).forEach((v: Item, i: number) => {
          const a = v.assessment,
            s = v.study,
            u = v.unit
          added.push(
            {
              id: `u:${u.id}`,
              position: { x: x + 520, y: y + i * 145 },
              data: {
                label: v.candidate || "Claim–plant unit",
                kind: "Claim–plant unit",
                text: "Candidate pairing",
              },
              className: "flow-candidate",
            },
            {
              id: `a:${a.id}`,
              position: { x: x + 780, y: y + i * 145 },
              data: {
                label: `${value(a.applicability)} · ${value(a.finding)}`,
                kind: "Study assessment",
                text: `${value(a.evidence_type)} · ${value(a.review_status)}`,
              },
              className: "flow-claim",
            },
            {
              id: `s:${s.id}`,
              position: { x: x + 1040, y: y + i * 145 },
              data: {
                label: s.title,
                kind: "Study",
                text: value(s.source_study_id),
              },
              className: "flow-candidate",
            },
          )
          links.push(
            {
              id: `uc:${u.id}`,
              source: `u:${u.id}`,
              target: `c:${info.ref}`,
              label: "about claim",
            },
            {
              id: `au:${a.id}`,
              source: `a:${a.id}`,
              target: `u:${u.id}`,
              label: "assesses unit",
            },
            {
              id: `as:${a.id}`,
              source: `a:${a.id}`,
              target: `s:${s.id}`,
              label: "assesses study",
            },
          )
        })
      }
      setNodes((existing) =>
        Array.from(
          new Map([...existing, ...added].map((n) => [n.id, n])).values(),
        ),
      )
      setEdges((existing) =>
        Array.from(
          new Map([...existing, ...links].map((n) => [n.id, n])).values(),
        ),
      )
      if (!added.length)
        setGraphError("No linked records were found to expand.")
    } catch (e) {
      setGraphError((e as Error).message)
    } finally {
      setGraphLoading(false)
    }
  }
  return (
    <div>
      <p>
        Dashed links are proposed historical identifications. Select a node to
        inspect it; use the controls to zoom or fit the view.
      </p>
      <p className="eyebrow">
        Showing up to 8 candidates and 8 claims. Explore the complete lists in
        their tabs.
      </p>
      <div className="live-graph">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          minZoom={0.15}
          maxZoom={1.6}
          onNodeClick={(_, node) =>
            setInfo({ ...node.data, position: node.position })
          }
        >
          <Background color="#d8d5c9" gap={22} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {info && (
        <div className="drawer-note">
          <strong>{value(info.kind)}</strong>
          <p>{value(info.label)}</p>
          <p>{value(info.text)}</p>
          {(info.kind === "Proposed identification" ||
            info.kind === "Extracted historical claim") && (
            <button
              className="secondary-button"
              disabled={graphLoading}
              onClick={expand}
            >
              {graphLoading ? "Loading…" : "Expand related evidence in graph"}
            </button>
          )}
          {graphError && <p role="alert">{graphError}</p>}
          {info.kind === "Proposed identification" && (
            <button
              className="source-link"
              onClick={() => openCandidate(info.ref)}
            >
              Inspect identification and evidence →
            </button>
          )}
          {info.kind === "Extracted historical claim" && (
            <button className="source-link" onClick={() => openClaim(info.ref)}>
              Inspect claim and studies →
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default function LiveApp() {
  const [section, setSection] =
    useState<"explore" | "record" | "map" | "sources" | "about">("explore")
  const [tab, setTab] = useState<Tab>("overview")
  const [book, setBook] = useState("")
  const [tierFilter, setTierFilter] = useState("")
  const [familyFilter, setFamilyFilter] = useState("")
  const [conceptFilter, setConceptFilter] = useState("")
  const [researchOnly, setResearchOnly] = useState(false)
  const [filterTerms, setFilterTerms] = useState({ family: "", concept: "" })
  const [search, setSearch] = useState("")
  const [searchTerm, setSearchTerm] = useState("")
  const [offset, setOffset] = useState(0)
  const [list, setList] = useState<{ items: Item[]; has_more: boolean }>({
    items: [],
    has_more: false,
  })
  const [record, setRecord] = useState<Entry | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(
    null,
  )
  const [candidateDetails, setCandidateDetails] = useState<Item | null>(null)
  const [selectedClaim, setSelectedClaim] = useState<string | null>(null)
  const [claimDetails, setClaimDetails] = useState<Item | null>(null)
  const [evidenceOffset, setEvidenceOffset] = useState(0)
  const [studyOffset, setStudyOffset] = useState(0)
  const [showHidden, setShowHidden] = useState(false)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState("")
  const [detailError, setDetailError] = useState("")
  const [mobileNav, setMobileNav] = useState(false)
  const [view, setView] = useState<"grid" | "list">("grid")
  const [brokenImages, setBrokenImages] = useState<Set<string>>(() => new Set())
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchTerm(search)
      setOffset(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])
  useEffect(() => {
    const timer = setTimeout(
      () => setFilterTerms({ family: familyFilter, concept: conceptFilter }),
      300,
    )
    return () => clearTimeout(timer)
  }, [familyFilter, conceptFilter])
  useEffect(() => {
    let active = true
    setLoading(true)
    setError("")
    api<{ items: Item[]; has_more: boolean }>(
      `/entries?identified=1&q=${encodeURIComponent(searchTerm)}&book=${book}&tier=${tierFilter}&family=${encodeURIComponent(filterTerms.family)}&concept=${encodeURIComponent(filterTerms.concept)}&research=${
        researchOnly ? "1" : "0"
      }&offset=${offset}`,
    )
      .then((x) => {
        if (active) setList(x)
      })
      .catch((e) => {
        if (active) setError(e.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [searchTerm, book, tierFilter, filterTerms, researchOnly, offset])
  useEffect(() => {
    if (!selectedCandidate) return
    let active = true
    setDetailLoading(true)
    setDetailError("")
    api<Item>(`/candidates/${selectedCandidate}?offset=${evidenceOffset}`)
      .then((x) => {
        if (active) setCandidateDetails(x)
      })
      .catch((e) => {
        if (active) setDetailError(e.message)
      })
      .finally(() => {
        if (active) setDetailLoading(false)
      })
    return () => {
      active = false
    }
  }, [selectedCandidate, evidenceOffset])
  useEffect(() => {
    if (!selectedClaim) return
    let active = true
    setDetailLoading(true)
    setDetailError("")
    api<Item>(`/claims/${selectedClaim}?offset=${studyOffset}`)
      .then((x) => {
        if (active) setClaimDetails(x)
      })
      .catch((e) => {
        if (active) setDetailError(e.message)
      })
      .finally(() => {
        if (active) setDetailLoading(false)
      })
    return () => {
      active = false
    }
  }, [selectedClaim, studyOffset])
  useEffect(() => {
    if (selectedClaim && tab === "studies") {
      const frame = requestAnimationFrame(() =>
        document
          .getElementById("research-detail")
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      )
      return () => cancelAnimationFrame(frame)
    }
  }, [selectedClaim, tab])
  const visible = useMemo(
    () =>
      record?.candidates.filter(
        (x) =>
          showHidden || x.decision?.tier === "A" || x.decision?.tier === "B",
      ) || [],
    [record, showHidden],
  )
  const currentCandidate = record?.candidates.find(
    (x) => x.hypothesis.id === selectedCandidate,
  )
  const currentClaim = record?.claims.find((x) => x.claim.id === selectedClaim)
  const openEntry = async (id: string, target?: { tab: "identification" | "studies"; id: string; includeHidden?: boolean }) => {
    setSection("record")
    setTab(target?.tab || "overview")
    setRecord(null)
    setLoading(true)
    setError("")
    setSelectedCandidate(target?.tab === "identification" ? target.id : null)
    setSelectedClaim(target?.tab === "studies" ? target.id : null)
    setShowHidden(Boolean(target?.includeHidden))
    try {
      setRecord(await api<Entry>(`/entries/${id}`))
      window.scrollTo({ top: 0 })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  const openCandidate = (id: string) => {
    setSelectedCandidate(id)
    setCandidateDetails(null)
    setEvidenceOffset(0)
    setTab("identification")
  }
  const openClaim = (id: string) => {
    setSelectedClaim(id)
    setClaimDetails(null)
    setStudyOffset(0)
    setTab("studies")
  }
  const navigate = (s: typeof section) => {
    setSection(s)
    setMobileNav(false)
    window.scrollTo({ top: 0 })
  }
  return (
    <div className="app-shell">
      <header className="site-header">
        <button
          className="brand"
          onClick={() => navigate("explore")}
          aria-label="EthnoTrace home"
        >
          <span className="brand-mark">
            <span />
          </span>
          <span>
            <strong>EthnoTrace</strong>
            <small>Historical botanical research</small>
          </span>
        </button>
        <button
          className="menu-button"
          onClick={() => setMobileNav(!mobileNav)}
        >
          {mobileNav ? "Close" : "Menu"}
        </button>
        <nav
          className={mobileNav ? "primary-nav open" : "primary-nav"}
          aria-label="Primary navigation"
        >
          <button
            className={
              section === "explore" || section === "record" ? "active" : ""
            }
            onClick={() => navigate("explore")}
          >
            Explore
          </button>
          <button
            className={section === "map" ? "active" : ""}
            onClick={() => navigate("map")}
          >
            Knowledge Map
          </button>
          <button
            className={section === "sources" ? "active" : ""}
            onClick={() => navigate("sources")}
          >
            Historical Sources
          </button>
          <button
            className={section === "about" ? "active" : ""}
            onClick={() => navigate("about")}
          >
            About
          </button>
        </nav>
      </header>
      {section === "map" && <KnowledgeMap openEntry={openEntry} />}
      {section === "explore" && (
        <main>
          <section className="catalog-intro">
            <p className="eyebrow">Explore the collection</p>
            <h1>Historical plants, traced to the present</h1>
            <p>
              Browse historical records and investigate their proposed
              connections to modern taxonomy and scientific research.
            </p>
            <div className="browse-modes">
              <button
                className={!book ? "active" : ""}
                onClick={() => {
                  setBook("")
                  setOffset(0)
                }}
              >
                All entries
              </button>
              <button
                className={book === "culpeper" ? "active" : ""}
                onClick={() => {
                  setBook("culpeper")
                  setOffset(0)
                }}
              >
                Culpeper
              </button>
              <button
                className={book === "dioscorides" ? "active" : ""}
                onClick={() => {
                  setBook("dioscorides")
                  setOffset(0)
                }}
              >
                Dioscorides
              </button>
            </div>
          </section>
          <div className="catalog-layout">
            <aside className="filters">
              <div className="filter-heading">
                <h2>Refine</h2>
                <button
                  onClick={() => {
                    setBook("")
                    setSearch("")
                    setTierFilter("")
                    setFamilyFilter("")
                    setConceptFilter("")
                    setResearchOnly(false)
                    setOffset(0)
                  }}
                >
                  Clear all
                </button>
              </div>
              <label className="filter-group">
                <span>Historical source</span>
                <select
                  value={book}
                  onChange={(e) => {
                    setBook(e.target.value)
                    setOffset(0)
                  }}
                >
                  <option value="">Both books</option>
                  <option value="culpeper">Culpeper</option>
                  <option value="dioscorides">Dioscorides</option>
                </select>
              </label>
              <div className="filter-group">
                <label htmlFor="tier-filter">Identification status</label>
                <InfoTip
                  label="Identification status filter"
                  text="The catalogue shows entries with an eligible or possible scientific name. Neither status proves historical identity."
                />
                <select
                  id="tier-filter"
                  value={tierFilter}
                  onChange={(e) => {
                    setTierFilter(e.target.value)
                    setOffset(0)
                  }}
                >
                  <option value="">Eligible and possible</option>
                  <option value="A">Meets identification criteria</option>
                  <option value="B">Possible identification</option>
                </select>
              </div>
              <div className="filter-group">
                <label htmlFor="concept-filter">Medicinal concept (MeSH)</label>
                <InfoTip
                  label="Medicinal concept filter"
                  text="Find entries with a claim mapped to a MeSH medical concept. A mapping is a recorded interpretation, not proof of effectiveness."
                />
                <input
                  id="concept-filter"
                  value={conceptFilter}
                  onChange={(e) => {
                    setConceptFilter(e.target.value)
                    setOffset(0)
                  }}
                  placeholder="e.g. Menstruation"
                />
              </div>
              <div className="filter-group">
                <label htmlFor="family-filter">Scientific family</label>
                <InfoTip
                  label="Scientific family filter"
                  text="Find entries with at least one candidate assigned to the specified botanical family."
                />
                <input
                  id="family-filter"
                  value={familyFilter}
                  onChange={(e) => {
                    setFamilyFilter(e.target.value)
                    setOffset(0)
                  }}
                  placeholder="e.g. Apiaceae"
                />
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={researchOnly}
                  onChange={(e) => {
                    setResearchOnly(e.target.checked)
                    setOffset(0)
                  }}
                />{" "}
                Modern research assessed
              </label>
              <p>
                Filters match the historical entry and may refer to different
                candidates or claims. Search historical names, Greek names,
                scientific names, or recorded synonyms.
              </p>
            </aside>
            <section className="catalog">
              <div className="catalog-tools">
                <label className="search">
                  <span aria-hidden="true">⌕</span>
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search historical or scientific names"
                    aria-label="Search historical or scientific names"
                  />
                </label>
                <div className="view-toggle">
                  <button
                    aria-label="Grid view"
                    aria-pressed={view === "grid"}
                    className={view === "grid" ? "active" : ""}
                    onClick={() => setView("grid")}
                  >
                    ▦
                  </button>
                  <button
                    aria-label="List view"
                    aria-pressed={view === "list"}
                    className={view === "list" ? "active" : ""}
                    onClick={() => setView("list")}
                  >
                    ☰
                  </button>
                </div>
              </div>
              <div className="results-note">
                <span>
                  {loading
                    ? "Searching…"
                    : `Showing ${offset + 1}–${offset + list.items.length}`}
                </span>
                <span>Historical entries with proposed identifications</span>
              </div>
              {error && (
                <div className="empty" role="alert">
                  <h3>Could not load records</h3>
                  <p>{error}</p>
                </div>
              )}
              {!error && !loading && list.items.length === 0 && (
                <div className="empty">
                  <h3>No matching records</h3>
                  <p>Try a different name or source.</p>
                </div>
              )}
              <div className={`plant-collection ${view}`}>
                {!error &&
                  list.items.map((p) => (
                    <article className="plant-card-shell" key={p.id}>
                    <button
                      className="plant-card live-card"
                      onClick={() => openEntry(p.id)}
                    >
                      <div className="live-plate" aria-hidden="true">
                        <span className="live-plate-placeholder">✳</span>
                        {p.image?.image_url && !brokenImages.has(p.image.image_url) && <img src={p.image.image_url} loading="lazy" alt="" onError={() => setBrokenImages(previous => new Set(previous).add(p.image.image_url))} />}
                      </div>
                      <div className="plant-card-copy">
                        <span className="record-source">
                          {bookName(p.book)} {p.chapter && `· ${p.chapter}`}
                        </span>
                        <h3>{p.name || p.chapter}</h3>
                        <em>{p.preferred_scientific_name || "Scientific name not recorded"}</em>
                      </div>
                    </button>
                    {p.image && !brokenImages.has(p.image.image_url) && (
                      <p className="plant-image-credit">
                        Proposed candidate photo · {p.image.creator} ·{" "}
                        <a href={p.image.license_url} target="_blank" rel="noreferrer">Licence</a>{" · "}
                        <a href={p.image.image_source_url || p.image.occurrence_url} target="_blank" rel="noreferrer">Image source</a>
                      </p>
                    )}
                    </article>
                  ))}
              </div>
              <div className="pagination">
                <button
                  className="secondary-button"
                  disabled={offset === 0 || loading}
                  onClick={() => setOffset(Math.max(0, offset - 24))}
                >
                  Previous
                </button>
                <button
                  className="secondary-button"
                  disabled={!list.has_more || loading}
                  onClick={() => setOffset(offset + 24)}
                >
                  Next
                </button>
              </div>
            </section>
          </div>
        </main>
      )}
      {section === "record" && (
        <main className="record-main">
          <button className="record-back" onClick={() => navigate("explore")}>
            ‹ Back to collection
          </button>
          {loading && <p>Loading historical record…</p>}
          {error && (
            <div className="empty" role="alert">
              <h3>Could not load record</h3>
              <p>{error}</p>
            </div>
          )}
          {record && (
            <>
              <div className="breadcrumbs">
                <button onClick={() => navigate("explore")}>Explore</button>
                <span>/</span>
                <span>{record.entry.name || record.entry.label}</span>
              </div>
              <div className="record-hero">
                <div className="record-plate live-record-plate">
                  <div className="record-plate-placeholder" aria-hidden="true">✳</div>
                  {record.image?.image_url && !brokenImages.has(record.image.image_url) ? (
                    <>
                      <img src={record.image.image_url} alt={`Photograph of proposed candidate ${record.preferred_scientific_name || ""}`} onError={() => setBrokenImages(previous => new Set(previous).add(record.image!.image_url))} />
                      <div className="record-image-credit">
                        <strong>Proposed candidate</strong>
                        <em>{record.preferred_scientific_name}</em>
                        <div>Photo: {record.image.creator}</div>
                        <div><a href={record.image.license_url} target="_blank" rel="noreferrer">Licence</a>{" · "}<a href={record.image.image_source_url || record.image.occurrence_url} target="_blank" rel="noreferrer">Image source</a></div>
                      </div>
                    </>
                  ) : <span>Historical record</span>}
                </div>
                <div className="record-heading">
                  <p className="eyebrow">
                    {bookName(record.entry.book)} ·{" "}
                    {record.entry.label
                      ? `Chapter ${record.entry.label}`
                      : `Page ${value(record.page)}`}
                  </p>
                  <h1>{record.entry.name || record.entry.label}</h1>
                  {record.preferred_scientific_name && <p className="record-scientific-name"><em>{record.preferred_scientific_name}</em><small>Proposed scientific identification</small></p>}
                  {(record.description || record.introduction || record.opening || record.historical_text) ? (
                    <>
                      <p className="record-description">{(record.description || record.introduction || record.opening || record.historical_text || "").slice(0, 280)}{(record.description || record.introduction || record.opening || record.historical_text || "").length > 280 ? "…" : ""}</p>
                      <button className="record-read-source" onClick={() => setTab("history")}>Read the complete historical record →</button>
                    </>
                  ) : <p>No historical description was recorded for this entry.</p>}
                </div>
              </div>
              <nav className="record-tabs" aria-label="Record sections">
                {([
                  ["overview", "Overview"],
                  ["history", "Historical Record"],
                  ["identification", "Identification"],
                  ["uses", "Claims & Research"],
                  ["relationships", "Relationships"],
                ] as [Tab, string][]).map(([id, label]) => (
                  <button
                    className={
                      tab === id || (id === "uses" && tab === "studies")
                        ? "active"
                        : ""
                    }
                    key={id}
                    onClick={() => setTab(id)}
                    title={tabHelp[id]}
                  >
                    {label}
                  </button>
                ))}
              </nav>
              <div className="record-content">
                {tab === "overview" && <PlantDashboard record={record} onCandidate={(id, includeHidden) => { setShowHidden(includeHidden); openCandidate(id) }} onClaim={openClaim} onHistory={() => setTab("history")} onResearch={() => setTab("uses")} />}
                {tab === "history" && (
                  <section>
                    <p className="eyebrow">Original historical source</p>
                    <h2>Historical record</h2>
                    <p>
                      {bookName(record.entry.book)}{" "}
                      {record.entry.label && `· Chapter ${record.entry.label}`}{" "}
                      {record.page && `· Page ${record.page}`}
                    </p>
                    {record.historical_text && (
                      <blockquote className="archival-quote">
                        <p
                          lang={
                            record.entry.book === "dioscorides"
                              ? "grc"
                              : undefined
                          }
                        >
                          {record.historical_text}
                        </p>
                      </blockquote>
                    )}
                    {record.introduction && (
                      <blockquote className="archival-quote">
                        <p>{record.introduction}</p>
                      </blockquote>
                    )}
                    <div className="historical-sections">
                      {([
                        ["Description", record.description, "The historical author's description of the subject."],
                        ["Place", record.place, "Where the historical author says the subject grows or is found."],
                        ["Time", record.season, "The historical author's observations about seasons or timing."],
                        ["Government and virtues", record.virtues, "The author's historical account of the subject's attributed properties and uses."],
                      ] as [string, string | undefined, string][]).map(
                        ([label, text, explanation]) =>
                          text && (
                            <section className="historical-section-card" key={label}>
                              <div className="historical-section-heading">
                                <h3>{label}</h3>
                                <InfoTip label={label} text={explanation} />
                              </div>
                              <p className="historical-section-text">{text}</p>
                            </section>
                          ),
                      )}
                    </div>
                    {!record.historical_text &&
                      !record.introduction &&
                      !record.description &&
                      !record.place &&
                      !record.season &&
                      !record.virtues && (
                        <p>
                          No original passage is available in the imported
                          entry.
                        </p>
                      )}
                    <section className="historical-names-card">
                      <div className="historical-section-heading">
                        <h3>Recorded historical names</h3>
                        <InfoTip label="Recorded historical names" text="Names recorded for this historical entry, with their source layer and quotation when available. They do not by themselves establish a modern identification." />
                      </div>
                      {record.names.length ? (
                        <ul className="historical-name-list">
                          {record.names.map((n, i) => (
                            <li key={i}>
                              <div className="historical-name-title">
                                <strong>{value(n.name)}</strong>
                                <span>{value(n.layer)}</span>
                              </div>
                              {n.quote && <p>“{n.quote}”</p>}
                            </li>
                          ))}
                        </ul>
                      ) : <p className="classification-empty">No historical names recorded.</p>}
                    </section>
                  </section>
                )}
                {tab === "identification" && (
                  <section>
                    <p className="eyebrow">Botanical identification</p>
                    <h2>Candidate identifications</h2>
                    <p>
                      These are hypotheses. An accepted taxonomic name does not
                      establish the identity of the historical plant.
                    </p>
                    <div
                      className="tier-legend"
                      aria-label="Eligibility categories"
                    >
                      {(["A", "B", "X"] as const).map((tier) => (
                        <div key={tier}>
                          <Status tier={tier} />
                          <InfoTip
                            label={tierText(tier)}
                            text={tierHelp[tier]}
                          />
                        </div>
                      ))}
                    </div>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={showHidden}
                        onChange={(e) => setShowHidden(e.target.checked)}
                      />{" "}
                      Show candidates excluded by the current criteria
                    </label>
                    {visible.length === 0 && (
                      <div className="empty">
                        No eligible or possible candidates were recorded for this entry.
                        Other candidates can be inspected using the option above.
                      </div>
                    )}
                    <div className="candidate-layout">
                      <div className="candidate-list">
                        {visible.map(({ hypothesis: h, decision: d }) => (
                          <button
                            key={h.id}
                            className={
                              selectedCandidate === h.id ? "active" : ""
                            }
                            onClick={() => openCandidate(h.id)}
                          >
                            <strong>
                              {h.accepted_name || "Unresolved candidate"}
                            </strong>
                            <Status tier={d?.tier} />
                          </button>
                        ))}
                      </div>
                      <div className="candidate-detail">
                        {!currentCandidate ? (
                          <p>
                            Select a candidate to inspect its rules and
                            supporting evidence.
                          </p>
                        ) : (
                          <>
                            <h3>
                              {currentCandidate.hypothesis.accepted_name ||
                                "Unresolved candidate"}
                            </h3>
                            <Status tier={currentCandidate.decision?.tier} />
                            <h3 className="detail-group-title">
                              Classification &amp; geography{" "}
                              <InfoTip
                                label="Classification and geography"
                                text="The recorded eligibility decision, its rules, source lineages, and geographical caveats for this candidate."
                              />
                            </h3>
                            <ClassificationSummary hypothesis={currentCandidate.hypothesis} decision={currentCandidate.decision} />
                            {detailLoading && <p>Loading evidence…</p>}
                            {detailError && <p role="alert">{detailError}</p>}
                            {candidateDetails && (
                              <>
                                <details className="detail-group" open>
                                  <summary>Taxonomic resolutions</summary>
                                  <p className="section-explanation">
                                    Compare the names and decisions recorded by
                                    each taxonomic authority.
                                  </p>
                                  <div className="source-detail-list">{candidateDetails.resolutions
                                    .filter((r: Item) => r.original_name)
                                    .map((r: Item, i: number) => <TaxonomicResolutionCard key={`${r.resolution_id}-${r.taxon_id || i}`} resolution={r} />)}</div>
                                </details>
                                <details className="detail-group" open>
                                  <summary>Evidence records</summary>
                                  <p className="section-explanation">
                                    Records linked to this candidate, with their
                                    sources and citation details.
                                  </p>
                                  {candidateDetails.evidence.length === 0 && (
                                    <p>
                                      No uniquely linked evidence records.
                                      Unlinked evidence remains associated with
                                      the historical entry.
                                    </p>
                                  )}
                                  <div className="source-detail-list">{candidateDetails.evidence.map((e: Item) => <EvidenceCard key={e.id} evidence={e} />)}</div>
                                  <div className="pagination">
                                    <button
                                      className="secondary-button"
                                      disabled={evidenceOffset === 0}
                                      onClick={() =>
                                        setEvidenceOffset(
                                          Math.max(0, evidenceOffset - 20),
                                        )
                                      }
                                    >
                                      Previous evidence
                                    </button>
                                    <button
                                      className="secondary-button"
                                      disabled={!candidateDetails.has_more}
                                      onClick={() =>
                                        setEvidenceOffset(evidenceOffset + 20)
                                      }
                                    >
                                      More evidence
                                    </button>
                                  </div>
                                </details>
                                <details className="detail-group">
                                  <summary>
                                    Botanical description comparison
                                  </summary>
                                  <p className="section-explanation">
                                    The recorded comparison of historical
                                    features with available botanical
                                    descriptions. A score is not independent
                                    proof of identity.
                                  </p>
                                  {candidateDetails.descriptions.length ===
                                    0 && (
                                    <p>
                                      Not assessed or no uniquely linked
                                      comparison.
                                    </p>
                                  )}
                                  {candidateDetails.descriptions.map(
                                    (d: Item, i: number) => (
                                      <section className="comparison-panel" key={i} aria-label="Recorded botanical description comparison">
                                        <div className="comparison-summary">
                                          <div><span className="comparison-label">Recorded verdict</span><strong>{value(d.comparison.verdict)}</strong></div>
                                          <div><span className="comparison-label">Congruence <InfoTip label="Congruence" text="The comparison's recorded score. It is not independent proof of historical identity." /></span><strong>{value(d.comparison.congruence)}</strong></div>
                                        </div>
                                        <div className="comparison-features">
                                          <p className="comparison-label">Feature comparisons</p>
                                          {d.scores.filter((s: Item) => s?.feature).length === 0 && <p className="classification-empty">No feature comparisons recorded.</p>}
                                          {d.scores.filter((s: Item) => s?.feature).map((s: Item, j: number) => (
                                            <article className="comparison-feature" key={j}>
                                              <div className="comparison-feature-heading"><h4>{s.feature}</h4><span className="comparison-feature-result">{value(s.label)}</span></div>
                                              <div className="comparison-feature-content"><span className="comparison-label">Recorded comparison</span><p>{value(s.reason)}</p></div>
                                              {s.historical_quote && <div className="comparison-feature-quote"><span className="comparison-label">Historical quotation</span><blockquote>“{s.historical_quote}”</blockquote></div>}
                                              {d.quotes_not_in_text?.includes(s.detail_id) && <p className="comparison-quote-warning">Quotation flagged as not found in source text</p>}
                                            </article>
                                          ))}
                                        </div>
                                      </section>
                                    ),
                                  )}
                                </details>
                              </>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                    <EntryEvidence id={record.entry.id} />
                  </section>
                )}
                {(tab === "uses" || tab === "studies") && (
                  <section>
                    <p className="eyebrow">Historical medicinal knowledge</p>
                    <h2>Recorded claims</h2>
                    <p>
                      These are extracted interpretations of historical
                      statements, not evidence of medical effectiveness.
                    </p>
                    {record.claims.length === 0 && (
                      <div className="empty">
                        No extracted claims were recorded for this entry.
                      </div>
                    )}
                    <div className="claims-list">
                      {record.claims.map(({ claim: c, concepts }) => (
                        <button className="claim-card" key={c.id} onClick={() => openClaim(c.id)}>
                          <span className="claim-card-top">
                            <span className="claim-card-id">Claim {c.source_claim_id.split(":").pop()}</span>
                            <span className="claim-card-action">Inspect claim <span aria-hidden="true">→</span></span>
                          </span>
                          <strong className="claim-card-title">{c.claim_text}</strong>
                          <span className="claim-card-quote">
                            <span className="claim-card-label">Historical quotation</span>
                            <span>{c.quote ? `“${c.quote}”` : "No quotation recorded"}</span>
                          </span>
                          <span className="claim-card-concepts">
                            <span className="claim-card-label">MeSH mappings</span>
                            <span className="claim-card-tags">
                              {concepts.length ? concepts.map((x: Item, i: number) => (
                                <span className="claim-card-tag" key={i}>{x.name} <span>({friendly(x.match)})</span></span>
                              )) : <span className="claim-card-empty">No mapped MeSH concept</span>}
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                {(tab === "uses" || tab === "studies") && (
                  <section id="research-detail" className="research-section">
                    <p className="eyebrow">Modern research</p>
                    <h2>
                      Studies and assessments{" "}
                      <InfoTip
                        label="Studies and assessments"
                        text="Studies are connected to specific claim–plant combinations. Assessments describe relevance and limitations; they are not proof that a remedy works."
                      />
                    </h2>
                    <p>
                      Select a historical claim to inspect the recorded studies
                      for its claim–plant units.
                    </p>
                    <label className="filter-group">
                      <span>Historical claim</span>
                      <select
                        value={selectedClaim || ""}
                        onChange={(e) => {
                          if (e.target.value) openClaim(e.target.value)
                        }}
                      >
                        <option value="">Select a claim</option>
                        {record.claims.map(({ claim: c }) => (
                          <option key={c.id} value={c.id}>
                            {c.claim_text}
                          </option>
                        ))}
                      </select>
                    </label>
                    {currentClaim && (
                      <>
                        <blockquote className="archival-quote">
                          <p>“{currentClaim.claim.quote}”</p>
                          <cite>
                            Historical quotation ·{" "}
                            {currentClaim.claim.source_claim_id}
                          </cite>
                        </blockquote>
                        <ClaimSummary claim={currentClaim.claim} concepts={currentClaim.concepts} />
                      </>
                    )}
                    {detailLoading && <p>Loading studies…</p>}
                    {detailError && <p role="alert">{detailError}</p>}
                    {claimDetails && (
                      <>
                        <Notice>
                          Studies and model-assisted assessments are not proof
                          of effectiveness. Review applicability, limitations
                          and the original publication.
                        </Notice>
                        <h3>Claim–plant combinations</h3>
                        {claimDetails.units.length === 0 && (
                          <p>No claim–plant unit was recorded.</p>
                        )}
                        {claimDetails.units.map((u: Item) => (
                          <p key={u.id}>
                            <strong>{value(u.candidate)}</strong> ·{" "}
                            {tierText(u.tier)} ·{" "}
                            {u.assessments
                              ? `${u.assessments} linked assessment${
                                  u.assessments === 1 ? "" : "s"
                                }`
                              : u.shared_unit_id
                                ? "Not assessed in the shared study set"
                                : "No uniquely linked assessment in the shared study set"}
                            {u.source_id_count > 1 &&
                              " · Source ID shared by multiple records"}
                            {u.link_status !== "unique" &&
                              " · Candidate link unresolved"}
                          </p>
                        ))}
                        {claimDetails.studies.length === 0 && (
                          <div className="empty">
                            Not assessed: no linked assessment was recorded for
                            this claim in the shared study set.
                          </div>
                        )}
                        <div className="study-list">
                          {claimDetails.studies.map((x: Item) => (
                            <article key={x.assessment.id}>
                              <div>
                                <p className="eyebrow">
                                  {value(x.study.source)} ·{" "}
                                  {value(x.study.publication_date)}
                                </p>
                                <h3>{x.study.title}</h3>
                                <p className="study-candidate">
                                  Candidate: {value(x.candidate)}
                                </p>
                                <h4>Recorded assessment</h4>
                                <AssessmentFacts
                                  values={[
                                    [
                                      "Evidence type",
                                      x.assessment.evidence_type,
                                    ],
                                    ["Relevance", x.assessment.relevance],
                                    ["Finding", x.assessment.finding],
                                    [
                                      "Applicability",
                                      x.assessment.applicability,
                                    ],
                                    ["Review", x.assessment.review_status],
                                  ]}
                                />
                                {x.assessment.review_flag && (
                                  <p className="review-flag">
                                    Flagged for review
                                  </p>
                                )}
                                <details className="assessment-details">
                                  <summary>
                                    Compatibility and limitations
                                  </summary>
                                  <p>
                                    How the recorded assessment compares this
                                    study with the historical claim.{" "}
                                    <InfoTip
                                      label="Compatibility"
                                      text={termHelp.Compatibility}
                                    />
                                  </p>
                                  <AssessmentFacts
                                    values={[
                                      ["Species", x.assessment.species_match],
                                      [
                                        "Condition",
                                        x.assessment.condition_match,
                                      ],
                                      [
                                        "Plant part",
                                        x.assessment.plant_part_match,
                                      ],
                                      [
                                        "Preparation",
                                        x.assessment.preparation_match,
                                      ],
                                      ["Route", x.assessment.route_match],
                                      ["Unknown", x.assessment.unknowns],
                                      ["Mismatches", x.assessment.mismatches],
                                    ]}
                                  />
                                </details>
                                {x.study.pmid && (
                                  <a
                                    href={`https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(x.study.pmid)}/`}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    PubMed {x.study.pmid} ↗
                                  </a>
                                )}
                                {!x.study.pmid && x.study.doi && (
                                  <a
                                    href={`https://doi.org/${encodeURIComponent(x.study.doi)}`}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    DOI {x.study.doi} ↗
                                  </a>
                                )}
                                {!x.study.pmid &&
                                  !x.study.doi &&
                                  safeHttps(x.source_url) && (
                                    <a
                                      href={safeHttps(x.source_url)}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      Open source record ↗
                                    </a>
                                  )}
                                <details>
                                  <summary>
                                    Supporting excerpts and provenance
                                  </summary>
                                  {x.excerpts
                                    .filter((a: Item) => a.text)
                                    .map((a: Item, i: number) => (
                                      <p key={i}>
                                        <strong>{a.field}:</strong> “{a.text}”
                                      </p>
                                    ))}
                                  <p>
                                    Source text: {value(x.study.text_locator)} ·
                                    Prompt: {value(x.assessment.prompt_version)}{" "}
                                    · Response:{" "}
                                    {value(x.assessment.raw_response_file)}
                                  </p>
                                </details>
                              </div>
                            </article>
                          ))}
                        </div>
                        <div className="pagination">
                          <button
                            className="secondary-button"
                            disabled={studyOffset === 0}
                            onClick={() =>
                              setStudyOffset(Math.max(0, studyOffset - 20))
                            }
                          >
                            Previous studies
                          </button>
                          <button
                            className="secondary-button"
                            disabled={!claimDetails.has_more}
                            onClick={() => setStudyOffset(studyOffset + 20)}
                          >
                            More studies
                          </button>
                        </div>
                        {claimDetails.related.length > 0 && (
                          <>
                            <h3>Related cross-book groupings</h3>
                            <p>
                              These are inferred groupings based on the recorded
                              species and medical concept; they do not establish
                              that remedies are equivalent.
                            </p>
                            {claimDetails.related.map((r: Item, i: number) => (
                              <button
                                className="source-link"
                                key={i}
                                onClick={() => openEntry(r.entry_id)}
                              >
                                {bookName(r.book)} · {r.name} {r.chapter} —{" "}
                                {r.claim} ({r.recorded_species};{" "}
                                {r.recorded_concept}) →
                              </button>
                            ))}
                          </>
                        )}
                      </>
                    )}
                  </section>
                )}
                {tab === "relationships" && (
                  <section>
                    <p className="eyebrow">Knowledge graph</p>
                    <h2>Explore relationships</h2>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={showHidden}
                        onChange={(e) => setShowHidden(e.target.checked)}
                      />{" "}
                      Include candidates excluded by the current criteria
                    </label>
                    <Graph
                      record={record}
                      visible={visible}
                      openCandidate={openCandidate}
                      openClaim={openClaim}
                    />
                  </section>
                )}
              </div>
            </>
          )}
        </main>
      )}
      {section === "sources" && (
        <main className="standard-page">
          <div className="section-head">
            <p className="eyebrow">The collection</p>
            <h1>Historical Sources</h1>
            <p>Explore the two historical works and their recorded entries.</p>
          </div>
          <div className="source-library">
            {(["culpeper", "dioscorides"] as const).map((b) => (
              <button
                key={b}
                onClick={() => {
                  setBook(b)
                  setOffset(0)
                  setSearch("")
                  setTierFilter("")
                  setFamilyFilter("")
                  setConceptFilter("")
                  setResearchOnly(false)
                  navigate("explore")
                }}
              >
                <span>Historical source</span>
                <h3>{bookName(b)}</h3>
                <p>
                  {b === "culpeper"
                    ? "The Complete Herbal"
                    : "De materia medica"}
                </p>
                <b>Browse entries →</b>
              </button>
            ))}
          </div>
        </main>
      )}
      {section === "about" && (
        <main className="standard-page about-page">
          <div className="section-head">
            <p className="eyebrow">About EthnoTrace</p>
            <h1>Following historical knowledge, carefully</h1>
          </div>
          <div className="about-grid">
            <div>
              <h3>Historical interpretation</h3>
              <p>
                EthnoTrace connects extracted historical statements to candidate
                botanical identifications. Names, taxonomic resolutions and
                source evidence are preserved for review.
              </p>
            </div>
            <div>
              <h3>Research with context</h3>
              <p>
                Modern publications and model-assisted assessments are presented
                with their limitations. A positive finding does not establish
                clinical efficacy or prove a historical identification.
              </p>
            </div>
          </div>
        </main>
      )}
      <footer>
        <div className="footer-brand">EthnoTrace</div>
        <p>A source-led historical botanical research project.</p>
        <button onClick={() => navigate("about")}>About this project</button>
      </footer>
    </div>
  )
}
