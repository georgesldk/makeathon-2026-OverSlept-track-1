import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react"
import { smoothResize } from "./details-animation"
import {
  ReactFlow,
  Background,
  Controls,
  Position,
  useEdgesState,
  useNodesState,
  type Node,
  type Edge,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import KnowledgeMap from "./KnowledgeMap"
import PlantDashboard from "./PlantDashboard"
import { claimRef, friendly, sizedImage, studyLink, tierLabel } from "./display"
import { Dropdown, ExpandableText, FilterPicker, Pager, SearchBox, buildSuggestions } from "./controls"
import Atlas from "./Atlas"
import PeerReview, { EntryReviews } from "./PeerReview"
import { DisplayMenu, TranslateButton } from "./accessibility"
import { romanize } from "./romanize"

// Slow, eased scrolling for every in-app move (the browser's own "smooth" is fast and not adjustable).
// Respects the system's reduced-motion setting.
const SCROLL_MS = 900
let scrollFrame = 0
function slowScrollTo(targetY: number | (() => number), duration = SCROLL_MS) {
  cancelAnimationFrame(scrollFrame)
  // the target may move while we travel (content above it still loading), so it is re-read every frame
  const target = () => Math.max(0, typeof targetY === "function" ? targetY() : targetY)
  const startY = window.scrollY
  if (Math.abs(target() - startY) < 2) return
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    window.scrollTo(0, target())
    return
  }
  const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
  const start = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / duration)
    window.scrollTo(0, startY + (target() - startY) * ease(t))
    if (t < 1) scrollFrame = requestAnimationFrame(step)
  }
  scrollFrame = requestAnimationFrame(step)
}
function slowScrollToElement(id: string, offset = window.innerWidth <= 760 ? 130 : 104) {
  const el = document.getElementById(id)
  if (el) slowScrollTo(() => el.getBoundingClientRect().top + window.scrollY - offset)
}
/** Keep a section at the same place on screen for a moment while content above it finishes loading. */
function holdAnchor(id: string | (() => Element | null | undefined), top: number, ms = 1500) {
  cancelAnimationFrame(scrollFrame)
  const until = performance.now() + ms
  const step = (now: number) => {
    const el = typeof id === "string" ? document.getElementById(id) : id()
    if (el) {
      const drift = el.getBoundingClientRect().top - top
      if (Math.abs(drift) > 1) window.scrollBy(0, drift)
    }
    if (now < until) scrollFrame = requestAnimationFrame(step)
  }
  scrollFrame = requestAnimationFrame(step)
}
// Stop the animation if the user scrolls by hand.
if (typeof window !== "undefined") {
  for (const ev of ["wheel", "touchstart", "keydown"]) {
    window.addEventListener(ev, () => cancelAnimationFrame(scrollFrame), { passive: true })
  }
}


type Item = Record<string, any>
type Tab = "overview" | "history" | "identification" | "uses" | "studies" | "relationships" | "review"
// The record page is one long page: every section is shown, one under the other, and the side menu scrolls to it.
const SECTION_ID: Record<Tab, string> = {
  overview: "sec-overview", history: "sec-history", identification: "sec-identification",
  uses: "sec-uses", studies: "research-detail", relationships: "sec-relationships", review: "sec-review",
}
const afterRender = (fn: () => void) => requestAnimationFrame(() => requestAnimationFrame(fn))
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
const BOOK_NAMES: Record<string, string> = { culpeper: "Culpeper", dioscorides: "Dioscorides", shennong: "Shennong" }
const bookName = (book: string) => BOOK_NAMES[book] || book
const BOOK_LANG: Record<string, string> = { dioscorides: "grc", shennong: "zh-Hant" }

/** A Greek or Chinese name in Latin script, in small type under the name. */
function RomanizedName({ name }: { name?: string | null }) {
  const [reading, setReading] = useState<Awaited<ReturnType<typeof romanize>>>(null)
  useEffect(() => {
    let active = true
    setReading(null)
    romanize(name).then((r) => { if (active) setReading(r) }).catch(() => {})
    return () => { active = false }
  }, [name])
  if (!reading) return null
  return (
    <p className="record-romanized" lang="en">
      <span>{reading.text}</span>
      <small>{reading.kind === "greek" ? "Latin transliteration" : "Pinyin (approximate)"}</small>
    </p>
  )
}
// Links for recorded source IDs (gbif:, clb:<dataset>:<id>, ncbi:, wikidata:, inat:)
const sourceUrl = (id: unknown): string | undefined => {
  if (typeof id !== "string") return undefined
  let m
  if ((m = /^gbif:(\d+)$/.exec(id))) return `https://www.gbif.org/species/${m[1]}`
  if ((m = /^clb:(\d+):([A-Za-z0-9_.-]+)$/.exec(id))) return `https://www.checklistbank.org/dataset/${m[1]}/taxon/${encodeURIComponent(m[2])}`
  if ((m = /^ncbi:(\d+)$/.exec(id))) return `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${m[1]}`
  if ((m = /^wikidata:(Q\d+)$/.exec(id))) return `https://www.wikidata.org/wiki/${m[1]}`
  if ((m = /^inat:(\d+)$/.exec(id))) return `https://www.inaturalist.org/taxa/${m[1]}`
  return undefined
}
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

// Historical Sources page (2026-11-07). Facts: Wikipedia (Nicholas Culpeper; Vienna Dioscurides) and
// Encyclopaedia Britannica (Pedanius Dioscorides), checked 7 Nov 2026.
const SOURCE_TIMELINE = [
  { year: "c. AD 77", text: "Dioscorides completes De materia medica" },
  { year: "1st–2nd c. AD", text: "The Shennong Bencao Jing is compiled in Eastern Han China" },
  { year: "c. 512", text: "The illustrated Vienna Dioscorides is made in Constantinople" },
  { year: "1649", text: "Culpeper translates the physicians' Latin pharmacopoeia into English" },
  { year: "1652–53", text: "Culpeper's English Physitian, later The Complete Herbal" },
  { year: "1799", text: "Sun Xingyan and Sun Fengyi reconstruct the lost Shennong Bencao Jing" },
  { year: "1906–14", text: "Max Wellmann's critical edition of the Greek text" },
]
const SOURCE_BOOKS = [
  {
    id: "dioscorides",
    era: "Greek · 1st century AD",
    title: "Dioscorides, De materia medica",
    subtitle: "Περὶ ὕλης ἰατρικῆς · “On medical material”",
    read: "https://scaife.perseus.org/reader/urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1:1.preface.1-1.preface.5/",
    author: [
      "Pedanius Dioscorides (c. AD 40–90) was a Greek physician from Anazarbus in Cilicia, in today's southern Turkey.",
      "He served as a surgeon with the armies of Emperor Nero, and the marches let him study plants and minerals across the Roman world himself rather than copy them from older books.",
    ],
    book: [
      "Written around AD 77 in five books, it describes nearly 600 plants and about 1,000 simple drugs: what each looks like, where it grows, how to prepare it, and what it treats.",
      "It was the leading pharmacological text for about sixteen centuries, copied, translated and annotated from Byzantium to the Islamic world and Renaissance Europe.",
    ],
    facts: [
      "The Vienna Dioscorides, made around 512 for the Byzantine princess Anicia Juliana, has 491 vellum leaves and more than 400 pictures. UNESCO added it to the Memory of the World register in 1997.",
      "Dioscorides grouped remedies by their effects on the body rather than alphabetically, unusual for his time.",
      "Many modern plant names, such as Anemone and Glycyrrhiza (liquorice), come from the Greek names he used.",
    ],
    edition: "Max Wellmann's Greek edition (1906–1914), read through the Scaife Viewer (Perseus).",
  },
  {
    id: "culpeper",
    era: "English · 1652–1653",
    title: "Culpeper, The Complete Herbal",
    subtitle: "First published as The English Physitian",
    read: "https://www.gutenberg.org/ebooks/49513",
    author: [
      "Nicholas Culpeper (1616–1654) studied at Cambridge and trained as an apothecary, then set up a practice in Spitalfields, outside the City of London's control, where he treated the poor for little or nothing, sometimes forty patients a morning.",
      "He fought for Parliament in the Civil War and was shot in the chest at the First Battle of Newbury in 1643. He never fully recovered, and died of tuberculosis at 37.",
    ],
    book: [
      "Sold cheaply and written in plain English so that ordinary people could treat themselves, the herbal gives for each plant its description, where and when it grows, and its “government and virtues”.",
      "Culpeper paired every herb with a ruling planet and combined astrology with the old theory of the four humours.",
    ],
    facts: [
      "In 1649 he translated the College of Physicians' Latin pharmacopoeia into English without permission, which made the physicians furious.",
      "The herbal has stayed in print continuously since the 17th century.",
      "He drew heavily on John Parkinson's Theatrum Botanicum of 1640.",
    ],
    edition: "The Complete Herbal, Project Gutenberg eBook #49513.",
  },
  {
    id: "shennong",
    era: "Chinese · 1st–2nd century AD",
    title: "The Shennong Bencao Jing",
    subtitle: "神農本草經 · “The Divine Farmer's Materia Medica”",
    read: "https://zh.wikisource.org/wiki/%E7%A5%9E%E8%BE%B2%E6%9C%AC%E8%8D%89%E7%B6%93_(%E5%AD%AB%E6%98%9F%E8%A1%8D)",
    author: [
      "No author is known. The book is attributed to Shennong, the legendary “Divine Farmer” said to have tasted hundreds of plants to learn which heal and which harm.",
      "Scholars think it gathers older oral traditions and was written down under the Eastern Han dynasty, in the 1st–2nd century AD.",
    ],
    book: [
      "Its 365 entries are sorted into three grades: 120 upper drugs that are harmless and nourish life, 120 middle drugs that treat illness but may be toxic, and 125 lower drugs with strong, often poisonous effects.",
      "Besides plants, it describes minerals and animal products. Only entries proposed as plants are identified here.",
    ],
    facts: [
      "The original text is lost. What survives was pieced together from quotations in later works.",
      "The upper grade includes ginseng, jujube and the lingzhi mushroom; the lower grade includes rhubarb root and peach and apricot kernels.",
    ],
    edition: "Sun Xingyan and Sun Fengyi's reconstruction (1799), Chinese Wikisource.",
  },
]
// About page licence list (from DATA_SOURCES.md, checked 3-4 Nov 2026)
const LICENCES = [["The historical texts", [["Culpeper, The Complete Herbal", "Project Gutenberg eBook #49513", "No copyright restriction (Project Gutenberg)"], ["Dioscorides, De materia medica", "Wellmann's Greek edition (1906–1914), First1KGreek TEI, via Perseus", "CC BY-SA 4.0"], ["Shennong Bencao Jing", "Sun Xingyan's edition (1799), Chinese Wikisource", "Text public domain; transcription CC BY-SA 4.0"], ["Bretschneider, Botanicon Sinicum III (1895)", "Biodiversity Heritage Library, item 23159", "Public domain"], ["Liddell–Scott–Jones Greek lexicon", "Perseus Digital Library", "CC BY-SA"]]], ["Plant names and identification", [["World Flora Online (Plant List 2026-06)", "", "CC0"], ["WCVP, World Checklist of Vascular Plants", "Royal Botanic Gardens, Kew", "CC BY 3.0"], ["IPNI, International Plant Names Index", "via the hackathon API", "CC BY 3.0"], ["GBIF", "", "CC BY 4.0 (some common names CC BY-NC)"], ["ChecklistBank and Catalogue of Life", "", "Per checklist; Catalogue of Life CC BY 4.0"], ["Wikidata", "", "CC0"], ["NCBI Taxonomy", "", "Public domain"], ["iNaturalist", "", "Not stated"], ["Dr. Duke's Phytochemical and Ethnobotanical Databases", "USDA", "CC0"], ["Global Names Verifier", "", "Each record keeps its database's licence"]]], ["Plant descriptions and ranges", [["Biodiversity Heritage Library", "scanned floras", "Mostly public domain; BHL data CC0"], ["Wikipedia (English)", "", "CC BY-SA 4.0"], ["WGSRPD region outlines (Atlas)", "TDWG, Brummitt 2001", "Not stated in the TDWG repository"]]], ["Medicine and modern research", [["MeSH, Medical Subject Headings", "Courtesy of the U.S. National Library of Medicine", "Public domain"], ["Disease Ontology", "", "CC0"], ["PubMed and NCBI E-utilities", "", "NCBI usage guidelines"], ["Europe PMC", "EMBL-EBI", "Each article keeps its own licence (open access only)"], ["ClinicalTrials.gov", "NLM", "Public domain"], ["EMA herbal monographs", "European Medicines Agency", "Reproduced with the source acknowledged"], ["Lardos et al. 2024", "research data, used for testing only", "Paper CC BY 4.0; data not redistributed"]]], ["Photographs", [["Candidate photos from GBIF (mostly iNaturalist)", "creator and licence shown with each photo", "CC0, CC BY or CC BY-SA only"], ["Candidate photos from Wikimedia Commons", "via Wikidata; creator and licence shown with each photo", "CC0, public domain, CC BY or CC BY-SA only"]]]]

const EXCERPT_LABELS: Record<string, string> = {
  relevance: "Why it is relevant", evidence_type: "Type of evidence", species: "Plant studied", condition: "Condition",
  therapeutic_action: "Effect studied", plant_part: "Plant part", preparation: "Preparation", route: "How it was given",
  outcome: "Result", safety: "Safety", harm: "Harm reported",
}
const tierHelp: Record<string, string> = {
  A: "Passed every rule: a real plant at species level with a settled name, named by at least two independent sources (or a scholar's reading of this passage confirmed by a second source), and it grew where the author lived. The best-supported reading, but still not proof.",
  B: "Plausible, but one check is missing or uncertain: for example only one source names it, the plant lists disagree on its name, or it may not have grown where the author lived.",
  X: "Excluded by the rules, for example the evidence is weak, it is only a genus, or it grows far from the author's world. Kept so it can be inspected; not shown by default.",
}
const tabHelp: Record<string, string> = {
  overview: "A summary of this historical entry and ways to explore it.",
  history: "The historical text and the names recorded for this entry.",
  identification:
    "Candidate modern identifications, eligibility rules, and supporting evidence.",
  uses: "Extracted historical claims, medical concept mappings, and connected research.",
  relationships: "A focused graph of the entry and its recorded relationships.",
  review: "Comments from domain experts confirming, disputing or annotating this entry.",
}
const termHelp: Record<string, string> = {
  Family:
    "A botanical family groups related plants. This is the family recorded for the candidate by the pipeline.",
  Rank: "The taxonomic level of the candidate, such as species, genus, or family.",
  "Selected by":
    "The taxonomic source used by the pipeline when selecting this candidate's accepted name.",
  Rules:
    "The identifiers of the eligibility rules applied by the pipeline to this candidate.",
  "Why it was excluded":
    "The rules that excluded this candidate. Only excluded candidates have reasons; for the others see the criteria above.",
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
  "Problems noted while reading the text":
    "Warnings the extraction step recorded for this claim, for example an uncertain quotation.",
  "Medical terms with no MeSH match":
    "Terms from the historical text that could not be matched to a MeSH heading, often old medical words.",
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

// Turn recorded identifiers into readable, clickable labels.
function lineageNode(text: unknown): React.ReactNode {
  const t = String(text ?? "")
  const cb = /^ChecklistBank project (\d+)$/.exec(t)
  if (cb)
    return <a href={`https://www.checklistbank.org/dataset/${cb[1]}`} target="_blank" rel="noreferrer" title="A separately published checklist in ChecklistBank; the number is its dataset ID">ChecklistBank checklist #{cb[1]} ↗</a>
  return t
}
function authorityLink(authority: unknown, id: unknown, name?: unknown): string | undefined {
  const a = String(authority || "").toLowerCase(), v = String(id || "")
  if (/^wfo-\d+$/i.test(v)) return `https://www.worldfloraonline.org/taxon/${v}`
  if (a.includes("wcvp") && /^\d+-\d$/.test(v)) return `https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:${v}`
  // WCVP's own record number has no public page: search Kew's Plants of the World Online by the name instead
  const bare = String(name || "").split(/\s+/).filter((w, i, all) => i < 2 || (["subsp.", "var.", "f."].includes(all[i - 1]) || ["subsp.", "var.", "f."].includes(w))).join(" ")
  if (a.includes("wcvp") && bare) return `https://powo.science.kew.org/results?q=${encodeURIComponent(bare)}`
  return undefined
}

/** A few entries of one book that have a photo, to start browsing from (sources page). */
function FeaturedEntries({ book, openEntry }: { book: string; openEntry: (id: string) => void }) {
  const [items, setItems] = useState<Item[]>([])
  useEffect(() => {
    let active = true
    api<{ items: Item[] }>(`/entries?identified=1&book=${book}&tier=A&limit=50`)
      .then((x) => { if (active) setItems(x.items.filter((i) => i.image?.image_url).slice(0, 4)) })
      .catch(() => {})
    return () => { active = false }
  }, [book])
  if (!items.length) return null
  return (
    <div className="featured">
      <p className="eyebrow">Start with these</p>
      <div className="featured-grid">
        {items.map((i) => (
          <button key={i.id} className="featured-card" onClick={() => openEntry(i.id)}>
            <img src={sizedImage(i.image.image_url, 640)} alt="" loading="lazy" />
            <span className="featured-copy">
              <em>{i.preferred_scientific_name}</em>
              <span>{i.name || i.chapter}{i.chapter && i.name ? ` · ${i.chapter}` : ""}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

function InfoTip({ label, text }: { label: string; text: string }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [alignRight, setAlignRight] = useState(false)
  const anchor = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    // keep the popover on screen: open leftwards when the icon is near the right edge
    if (open && anchor.current) setAlignRight(anchor.current.getBoundingClientRect().left + 290 > window.innerWidth - 16)
  }, [open])
  return (
    <span
      ref={anchor}
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
        <span className={`info-popover${alignRight ? " info-popover-right" : ""}`} role="tooltip" id={id}>
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
      <dd>{Array.isArray(content) && content.length > 0 ? <ul className="classification-notes">{content.map((item, index) => <li key={index}>{lineageNode(item)}</li>)}</ul> : typeof content === "string" && /^ChecklistBank project \d+$/.test(content) ? lineageNode(content) : value(content)}</dd>
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
          {Array.isArray(decision?.reasons) && decision.reasons.length > 0 && <FactTile label="Why it was excluded" content={decision.reasons} />}
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
        {lineages?.length ? <details className="lineage-list"><summary>{lineages.length} {lineages.length === 1 ? "lineage" : "lineages"} counted by the pipeline</summary><p className="lineage-help">Each independent source is counted once; sources that copy one another count as one. ChecklistBank checklists are separate published lists, numbered by their dataset ID.</p><ul>{lineages.map((lineage: string, i: number) => <li key={`${lineage}-${i}`}>{lineageNode(lineage)}</li>)}</ul></details> : <p className="classification-empty">{lineages ? "None recorded" : "Not recorded"}</p>}
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
        <p className="classification-kicker">How reliable is this reading? <InfoTip label="Reading the text" text="An AI model read the historical text and turned this passage into a claim. These notes record anything that went wrong while doing so. They are not an independent review." /></p>
        {(() => {
          const list = (v: unknown) => (Array.isArray(v) ? v : v ? [v] : []) as unknown[]
          const flags = list(claim.flags), unmapped = list(claim.mesh_not_found)
          if (!flags.length && !unmapped.length)
            return <p className="classification-empty">Nothing went wrong while reading this passage, and every medical term found a match in MeSH.</p>
          return (
            <dl className="classification-facts classification-facts-two">
              {flags.length > 0 && <FactTile label="Problems noted while reading the text" content={flags} />}
              {unmapped.length > 0 && <FactTile label="Medical terms with no MeSH match" content={unmapped} />}
            </dl>
          )
        })()}
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
        <div className="classification-fact">
          <dt>Authority ID<InfoTip label="Authority ID" text={termHelp["Authority ID"]} /></dt>
          <dd>{authorityLink(resolution.authority, resolution.source_id, resolution.accepted_name)
            ? <a href={authorityLink(resolution.authority, resolution.source_id, resolution.accepted_name)} target="_blank" rel="noreferrer">{value(resolution.source_id)} ↗</a>
            : value(resolution.source_id)}</dd>
        </div>
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
        {sourceUrl(e.source_record_id)
          ? <div className="classification-fact"><dt>Source record{termHelp["Source record"] && <InfoTip label="Source record" text={termHelp["Source record"]} />}</dt><dd><a href={sourceUrl(e.source_record_id)} target="_blank" rel="noreferrer">{String(e.source_record_id)} ↗</a></dd></div>
          : <FactTile label="Source record" content={e.source_record_id} />}
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
  // when the records arrive, grow the open box smoothly instead of jumping
  const box = useRef<HTMLDetailsElement>(null), before = useRef(0)
  useLayoutEffect(() => {
    if (box.current && data) smoothResize(box.current, before.current)
  }, [data])
  useEffect(() => {
    if (!opened) return
    let active = true
    setError("")
    setData(null)
    api<Item>(`/entries/${id}/evidence?offset=${offset}`)
      .then((x) => {
        if (!active) return
        before.current = box.current?.offsetHeight || 0
        setData(x)
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
      ref={box}
      className="detail-group"
      onToggle={(e) => setOpened(e.currentTarget.open)}
    >
      <summary>All entry evidence, including unlinked records</summary>
      <p className="section-explanation">
        Records that could not be matched to one candidate stay on the historical
        entry; they are not assigned to a candidate automatically.
      </p>
      {error && <p role="alert">{error}</p>}
      {opened && !data && !error && <p>Loading evidence…</p>}
      {data && (
        <>
          <div className="source-detail-list">{data.items.map((v: Item) => <EvidenceCard key={v.id} evidence={v} showLinkStatus />)}</div>
          <Pager page={offset / 20} hasMore={data.has_more} onPage={(n) => setOffset(n * 20)} label="Entry evidence pages" />
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
  // the nodes arrive after the first render, so centre the view again once they are in
  const flowRef = useRef<{ fitView: (o?: { padding?: number; duration?: number }) => unknown } | null>(null)
  const nodeCount = nodes.length
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  useEffect(() => {
    if (!nodeCount) return
    const frame = requestAnimationFrame(() => flowRef.current?.fitView({ padding: 0.15, duration: 400 }))
    return () => cancelAnimationFrame(frame)
  }, [nodeCount])
  const [info, setInfo] = useState<Item | null>(null)
  // drawn like the Knowledge Map: rounded boxes with their kind, name and detail; curved lines left to right
  const shownNodes = useMemo(() => nodes.map((n) => ({
    ...n, className: `${n.className || ""} map-node rel-node`, sourcePosition: Position.Right, targetPosition: Position.Left,
    data: { ...n.data, raw: n.data, label: <><span className="map-node-type">{String(n.data.kind || "")}</span><strong>{String(n.data.label || "Not recorded")}</strong>{n.data.text ? <small>{String(n.data.text)}</small> : null}</> },
  })), [nodes])
  const shownEdges = useMemo(() => edges.map((e) => ({
    ...e, type: "default",
    style: { ...(e.style || {}), stroke: (e.style as Item | undefined)?.strokeDasharray ? "var(--map-edge-dashed)" : "var(--map-edge)", strokeWidth: 1.6, opacity: 0.85 },
    labelStyle: { fill: "var(--map-label)", fontSize: 10 }, labelBgStyle: { fill: "var(--map-label-bg)", fillOpacity: 0.94 },
  })), [edges])
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState("")
  const candidates = visible.slice(0, 8)
  const claims = record.claims.slice(0, 8)   // the caller decides whether claims without MeSH are included
  useEffect(() => {
    // the book and the entry sit level with the middle of the column of identifications and claims
    const middle = Math.max(0, (candidates.length * 92 + 40 + claims.length * 84) / 2 - 40)
    const ns: Node[] = [
      {
        id: "book",
        position: { x: 0, y: middle },
        data: {
          label: bookName(record.entry.book),
          kind: "Historical source",
          text: record.book.source,
          url: SOURCE_BOOKS.find((b) => b.id === record.entry.book)?.read,
        },
        className: "flow-historical",
      },
      {
        id: "entry",
        position: { x: 250, y: middle },
        data: {
          label: record.entry.name || record.entry.label,
          kind: "Historical entry",
          text: record.entry.label || record.entry.entry_key,
        },
        className: "flow-historical",
      },
    ]
    const es: Edge[] = [
      { id: "book-entry", source: "book", target: "entry", label: "contains" },
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
        // one column under the identifications, so every line runs left to right
        position: { x: 540, y: candidates.length * 92 + 40 + i * 84 },
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
                  url: authorityLink(r.authority, r.source_id, r.accepted_name),
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
              url: sourceUrl(e.source_record_id),
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
              data: { label: c.name, kind: "MeSH concept", text: c.id, url: /^D\d+$/.test(String(c.id)) ? `https://id.nlm.nih.gov/mesh/${c.id}` : undefined },
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
                url: studyLink(s, v.source_url),
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
      <p className="section-explanation graph-explanation">
        Dashed links are proposed historical identifications. Select a node to
        inspect it; use the controls to zoom or fit the view. Showing up to 8
        candidates and 8 claims; the complete lists are in the sections above.
      </p>
      <div className="live-graph">
        <ReactFlow
          nodes={shownNodes}
          edges={shownEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={(instance) => { flowRef.current = instance }}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.15}
          maxZoom={1.6}
          onNodeClick={(_, node) =>
            setInfo({ ...((node.data as Item).raw || node.data), position: node.position })
          }
        >
          <Background color="var(--map-edge-faint)" gap={22} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {info && (
        <div className="drawer-note">
          <strong>{value(info.kind)}</strong>
          <p>{info.url ? <a className="drawer-title-link" href={info.url} target="_blank" rel="noreferrer">{value(info.label)} ↗</a> : value(info.label)}</p>
          <p>{value(info.text)}</p>
          <div className="drawer-actions">
          {info.url && <a className="source-link" href={info.url} target="_blank" rel="noreferrer">Open the source ↗</a>}
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
        </div>
      )}
    </div>
  )
}

export default function LiveApp() {
  const [section, setSection] =
    useState<"explore" | "record" | "map" | "atlas" | "review" | "sources" | "about">("explore")
  const [tab, setTab] = useState<Tab>("overview")
  const [book, setBook] = useState("")
  const [tierFilter, setTierFilter] = useState("")
  const [familyFilter, setFamilyFilter] = useState("")
  const [conceptFilter, setConceptFilter] = useState("")
  const [researchOnly, setResearchOnly] = useState(false)
  const [relevantOnly, setRelevantOnly] = useState(false)
  const [filterTerms, setFilterTerms] = useState({ family: "", concept: "" })
  const [search, setSearch] = useState("")
  const [searchTerm, setSearchTerm] = useState("")
  const [offset, setOffset] = useState(0)
  const [list, setList] = useState<{ items: Item[]; has_more: boolean; total?: number }>({
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
  const [graphUnmapped, setGraphUnmapped] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const [mapEntry, setMapEntry] = useState<string>("")
  const [reviewEntry, setReviewEntry] = useState<string>("")
  const openReview = (id: string) => { setReviewEntry(id); setSection("review"); slowScrollTo(0) }
  const openMap = (id: string) => { setMapEntry(id); setSection("map"); slowScrollTo(0) }
  const [graphHidden, setGraphHidden] = useState(false)
  const [facets, setFacets] = useState<{ families: { name: string; count: number }[]; concepts: { name: string; count: number }[]; books: Record<string, Item> } | null>(null)
  const [nameIndex, setNameIndex] = useState<{ id: string; name?: string; book: string; chapter?: string; sci?: string }[]>([])
  useEffect(() => {
    api<typeof facets>("/facets").then(setFacets).catch(() => setFacets(null))
    api<{ items: typeof nameIndex }>("/names").then((x) => setNameIndex(x.items)).catch(() => setNameIndex([]))
  }, [])
  const suggestions = useMemo(() => buildSuggestions(nameIndex, facets, bookName), [nameIndex, facets])
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
    api<{ items: Item[]; has_more: boolean; total?: number }>(
      `/entries?identified=1&q=${encodeURIComponent(searchTerm)}&book=${book}&tier=${tierFilter}&family=${encodeURIComponent(filterTerms.family)}&concept=${encodeURIComponent(filterTerms.concept)}&research=${
        researchOnly ? "1" : "0"
      }&relevant=${
        relevantOnly ? "1" : "0"
      }&offset=${offset}&grouped=1`,
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
  }, [searchTerm, book, tierFilter, filterTerms, researchOnly, relevantOnly, offset])
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
  // Scroll spy: the side menu highlights the section currently at the top of the screen.
  useEffect(() => {
    if (!record) return
    const order: Tab[] = ["overview", "history", "identification", "uses", "relationships", "review"]
    const onScroll = () => {
      let current: Tab = "overview"
      for (const t of order) {
        const el = document.getElementById(SECTION_ID[t])
        if (el && el.getBoundingClientRect().top <= 140) current = t
      }
      setTab(current)
    }
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [record])
  const goTo = (t: Tab) => {
    setTab(t === "studies" ? "uses" : t)
    afterRender(() => slowScrollToElement(SECTION_ID[t]))
  }
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
  // Keep all historical claims accessible, with mapped claims first.
  const meshClaims = record?.claims.filter((x) => x.concepts?.length) || []
  // George's call (2026-11-07): only claims mapped to a MeSH medical concept are listed; the rest are counted.
  const hiddenClaims = (record?.claims.length || 0) - meshClaims.length
  const [siblings, setSiblings] = useState<Item[]>([])
  useEffect(() => {
    setSiblings([])
    const name = record?.preferred_scientific_name
    if (!name) return
    let active = true
    api<{ items: Item[] }>(`/entries?identified=1&q=${encodeURIComponent(name)}&limit=50`)
      .then((x) => { if (active) setSiblings(x.items.filter((i) => i.preferred_scientific_name === name)) })
      .catch(() => {})
    return () => { active = false }
  }, [record?.entry.id, record?.preferred_scientific_name])
  const sourceSwitch = record && siblings.length > 1 ? (
    <span className="source-switch" role="group" aria-label="Same plant in other sources">
      {siblings.map((m) => {
        const twins = siblings.filter((x) => x.book === m.book).length > 1
        const current = m.id === record.entry.id
        return (
          <button key={m.id} type="button" className={current ? "active" : ""} aria-pressed={current}
            title={`${bookName(m.book)}${m.chapter ? ` · ${m.chapter}` : ""} · ${m.name || ""}`}
            onClick={(e) => {
              if (current) return
              // anchor on the switch that was clicked (its heading), not the section's top: a shorter section in the
              // other source would otherwise leave the reader in the next section
              const all = Array.from(document.querySelectorAll(".source-switch"))
              const index = all.indexOf(e.currentTarget.closest(".source-switch") as Element)
              openEntry(m.id, undefined, tab === "studies" ? "uses" : tab, index)
            }}>
            {bookName(m.book)}{twins ? ` · ${m.chapter || m.name}` : ""}
          </button>
        )
      })}
    </span>
  ) : null
  const [switching, setSwitching] = useState(false)
  const openEntry = async (id: string, target?: { tab: "identification" | "studies"; id: string; includeHidden?: boolean }, keep?: Tab, switchIndex = -1) => {
    if (keep && record) {
      // Switching to the same plant in another source: swap the content in place and keep the reader where they
      // are, instead of clearing the page and scrolling again.
      const clicked = switchIndex >= 0 ? () => document.querySelectorAll(".source-switch")[switchIndex] : null
      const anchorId = SECTION_ID[keep]
      const before = (clicked?.() || document.getElementById(anchorId))?.getBoundingClientRect().top ?? 0
      setSwitching(true)
      try {
        const next = await api<Entry>(`/entries/${id}`)
        setSelectedCandidate(null)
        setSelectedClaim(null)
        setCandidateDetails(null)
        setClaimDetails(null)
        setRecord(next)
        holdAnchor(clicked ? () => clicked() || document.getElementById(anchorId) : anchorId, before)
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setSwitching(false)
      }
      return
    }
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
      if (target) afterRender(() => slowScrollToElement(SECTION_ID[target.tab]))
      else if (keep) afterRender(() => slowScrollToElement(SECTION_ID[keep]))   // switching source: stay in the same section
      else slowScrollTo(0)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  const openCandidate = (id: string) => {
    if (tab === "identification") afterRender(() => slowScrollToElement("candidate-detail", 170))
    setSelectedCandidate(id)
    setCandidateDetails(null)
    setEvidenceOffset(0)
    if (tab !== "identification") goTo("identification")
  }
  const openClaim = (id: string) => {
    setSelectedClaim(id)
    setClaimDetails(null)
    setStudyOffset(0)
    goTo("studies")
  }
  const navigate = (s: typeof section) => {
    setSection(s)
    setMobileNav(false)
    slowScrollTo(0)
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
            className={section === "atlas" ? "active" : ""}
            onClick={() => navigate("atlas")}
          >
            Atlas
          </button>
          <button
            className={section === "map" ? "active" : ""}
            onClick={() => { setMapEntry(""); navigate("map") }}
          >
            Knowledge Map
          </button>
          <button
            className={section === "review" ? "active" : ""}
            onClick={() => { setReviewEntry(""); navigate("review") }}
          >
            Expert review
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
        <DisplayMenu />
      </header>
      {section === "map" && <KnowledgeMap key={mapEntry || "map"} openEntry={openEntry} initialEntryId={mapEntry} suggestions={suggestions} />}
      {section === "review" && <PeerReview key={reviewEntry || "review"} suggestions={suggestions} openEntry={openEntry} initialEntryId={reviewEntry} />}
      {section === "atlas" && <Atlas openEntry={openEntry} />}
      {section === "explore" && (
        <main>
          <section className="catalog-intro">
            <p className="eyebrow">Explore the collection</p>
            <h1>Historical plants, traced to the present</h1>
            <p>
              Browse historical records and investigate their proposed
              connections to modern taxonomy and scientific research.
            </p>

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
                    setRelevantOnly(false)
                    setOffset(0)
                  }}
                >
                  Clear all
                </button>
              </div>
              <div className="filter-group">
                <span className="filter-label">Historical source</span>
                <Dropdown
                  label="Historical source"
                  value={book}
                  onChange={(v) => {
                    setBook(v)
                    setOffset(0)
                  }}
                  options={[
                    { value: "", label: "All entries" },
                    { value: "culpeper", label: "Culpeper", hint: "The Complete Herbal, 1653" },
                    { value: "dioscorides", label: "Dioscorides", hint: "De materia medica, 1st century" },
                    { value: "shennong", label: "Shennong Bencao Jing", hint: "Han China, 1st–2nd century" },
                  ]}
                />
              </div>
              <div className="filter-group">
                <span className="filter-label">Identification status
                <InfoTip
                  label="Identification status"
                  text="How sure we are which modern plant the old name means. Identified: the plant passed every rule. It is a real plant at species level with a settled name, at least two independent sources agree on it (or a scholar's reading of this very passage is confirmed by a second source), and it grew where the author lived. Where the book describes the plant, the description also had to fit. Possible: the plant is plausible, but one of these checks is missing, for example only one source names it. Neither is proof of what the author meant."
                /></span>
                <Dropdown
                  id="tier-filter"
                  label="Identification status"
                  value={tierFilter}
                  onChange={(v) => {
                    setTierFilter(v)
                    setOffset(0)
                  }}
                  options={[
                    { value: "", label: "Identified or possible", hint: "Every entry with at least one proposed plant" },
                    { value: "A", label: "Identified", hint: "Passed every rule: two independent sources agree, and it grew where the author lived" },
                    { value: "B", label: "Possible only", hint: "Plausible, but one check is missing, e.g. only one source names it" },
                  ]}
                />
              </div>
              <div className="filter-group">
                <span className="filter-label"><label htmlFor="concept-filter">Medical use (MeSH)</label>
                <InfoTip
                  label="Medical use filter"
                  text="Find entries with a historical claim mapped to this MeSH medical concept. The boxes are the most common ones; the numbers are how many entries have them. A mapping is a reading of the old text, not proof that the remedy works."
                /></span>
                <FilterPicker
                  id="concept-filter"
                  value={conceptFilter}
                  items={facets?.concepts || []}
                  onChange={(v) => {
                    setConceptFilter(v)
                    setOffset(0)
                  }}
                  placeholder="Search medical uses"
                />
              </div>
              <div className="filter-group">
                <span className="filter-label"><label htmlFor="family-filter">Plant family</label>
                <InfoTip
                  label="Plant family filter"
                  text="Find entries with at least one proposed plant in this botanical family. The boxes are the most common families; the numbers are how many entries have them."
                /></span>
                <FilterPicker
                  id="family-filter"
                  value={familyFilter}
                  items={facets?.families || []}
                  onChange={(v) => {
                    setFamilyFilter(v)
                    setOffset(0)
                  }}
                  placeholder="Search families"
                />
              </div>
              <label className="check-row switch-row">
                <input
                  type="checkbox"
                  checked={researchOnly}
                  onChange={(e) => {
                    setResearchOnly(e.target.checked)
                    setOffset(0)
                  }}
                />
                <span>Only plants with modern studies</span>
              </label>
              <label className="check-row switch-row">
                <input
                  type="checkbox"
                  checked={relevantOnly}
                  onChange={(e) => {
                    setRelevantOnly(e.target.checked)
                    setOffset(0)
                  }}
                />
                <span>Only plants with a study relevant to a claim</span>
              </label>
              <p>
                Filters match the historical entry and may refer to different
                candidates or claims. Search historical names, Greek names,
                scientific names, or recorded synonyms.
              </p>
            </aside>
            <section className="catalog" id="catalog-top">
              <div className="catalog-tools">
                <SearchBox
                  value={search}
                  onChange={setSearch}
                  suggestions={suggestions}
                  label="Search plants, medical uses or plant families"
                  placeholder="Search a plant, a use (e.g. cough) or a family"
                  onPick={(x) => {
                    if (x.kind === "plant" && x.id) { setSearch(""); openEntry(x.id) }
                    else if (x.kind === "use") { setSearch(""); setConceptFilter(x.value); setOffset(0) }
                    else if (x.kind === "family") { setSearch(""); setFamilyFilter(x.value); setOffset(0) }
                  }}
                />
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
                      className={`plant-card live-card${p.members ? " grouped" : ""}`}
                      aria-expanded={p.members ? openGroup === p.id : undefined}
                      onClick={() => p.members ? setOpenGroup(openGroup === p.id ? null : p.id) : openEntry(p.id)}
                    >
                      <div className="live-plate" aria-hidden="true">
                        <span className="live-plate-placeholder">✳</span>
                        {p.image?.image_url && !brokenImages.has(p.image.image_url) && <img src={sizedImage(p.image.image_url, 640)} loading="lazy" decoding="async" alt="" onError={() => setBrokenImages(previous => new Set(previous).add(p.image.image_url))} />}
                      </div>
                      <div className="plant-card-copy">
                        {p.members ? (
                          <>
                            <span className="record-source">
                              {p.members.length} records · shared proposed name · {[...new Set(p.members.map((m: Item) => bookName(m.book)))].join(" & ")}
                            </span>
                            <h3 className="card-sci">{p.preferred_scientific_name}</h3>
                            <span className="card-common">{p.members.map((m: Item) => m.name || m.chapter).filter((v: string, i: number, a: string[]) => a.indexOf(v) === i).join(" · ")}</span>
                            <span className="group-toggle">{openGroup === p.id ? "Hide records ↑" : "Show the records ↓"}</span>
                          </>
                        ) : (
                          <>
                            <span className="record-source">
                              {bookName(p.book)} {p.chapter && `· ${p.chapter}`}
                            </span>
                            <h3 className={p.preferred_scientific_name ? "card-sci" : ""}>{p.preferred_scientific_name || p.name || p.chapter}</h3>
                            {p.preferred_scientific_name && <span className="card-common">{p.name || p.chapter}</span>}
                          </>
                        )}
                      </div>
                    </button>
                    {p.members && openGroup === p.id && (
                      <ul className="group-members">
                        {p.members.map((m: Item) => (
                          <li key={m.id}>
                            <button onClick={() => openEntry(m.id)}>
                              <span className="record-source">{bookName(m.book)}{m.chapter ? ` · ${m.chapter}` : ""}</span>
                              <strong>{m.name || m.chapter}</strong>
                              <span aria-hidden="true">→</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
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
              <Pager page={offset / 24} total={list.total !== undefined ? Math.ceil(list.total / 24) : undefined} hasMore={list.has_more} onPage={(n) => { setOffset(n * 24); slowScrollToElement("catalog-top") }} label="Result pages" />
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
                      <img src={sizedImage(record.image.image_url, 1024)} alt={`Photograph of proposed candidate ${record.preferred_scientific_name || ""}`} onError={() => setBrokenImages(previous => new Set(previous).add(record.image!.image_url))} />
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
                      ? `${record.entry.book === "shennong" ? "Entry" : "Chapter"} ${record.entry.label}`
                      : `Page ${value(record.page)}`}
                  </p>
                  <h1 lang={BOOK_LANG[record.entry.book]}>{record.entry.name || record.entry.label}</h1>
                  <RomanizedName name={record.entry.name} />
                  {record.preferred_scientific_name && <p className="record-scientific-name"><em>{record.preferred_scientific_name}</em><small>Proposed scientific identification</small></p>}
                  {(record.description || record.introduction || record.opening || record.historical_text) ? (
                    <>
                      <ExpandableText
                        className="record-description"
                        text={record.description || record.introduction || record.opening || record.historical_text || ""}
                      />
                      <TranslateButton key={`d-${record.entry.id}`} text={record.description || record.introduction || record.opening || record.historical_text} compact />
                      <button className="record-read-source" onClick={() => goTo("history")}>Read the complete historical record →</button>
                    </>
                  ) : <p>No historical description was recorded for this entry.</p>}
                </div>
              </div>
              <div className="record-layout">
              <nav className="record-tabs" aria-label="Record sections">
                <button className="record-tabs-back" onClick={() => navigate("explore")}>‹ Back to collection</button>
                {([
                  ["overview", "Overview"],
                  ["history", "Historical Record"],
                  ["identification", "Identification"],
                  ["uses", "Claims & Research"],
                  ["relationships", "Relationships"],
                  ["review", "Expert review"],
                ] as [Tab, string][]).map(([id, label]) => (
                  <button
                    className={
                      tab === id || (id === "uses" && tab === "studies")
                        ? "active"
                        : ""
                    }
                    key={id}
                    onClick={() => goTo(id)}
                    title={tabHelp[id]}
                  >
                    {label}
                  </button>
                ))}
              </nav>
              <div className={`record-content${switching ? " switching" : ""}`}>
                <div id="sec-overview" className="record-section"><PlantDashboard switcher={sourceSwitch} record={record} onCandidate={(id, includeHidden) => { setShowHidden(includeHidden); openCandidate(id) }} onClaim={openClaim} onHistory={() => goTo("history")} onResearch={() => goTo("uses")} /></div>
                {(
                  <section id="sec-history" className="record-section">
                    <p className="eyebrow">Original historical source</p>
                    <h2 className="with-switch"><span>Historical record</span>{sourceSwitch}</h2>
                    <p className="section-meta">
                      <span>{bookName(record.entry.book)}</span>
                      {record.entry.label && <span>Chapter {record.entry.label}</span>}
                      {record.page && <span>Page {record.page}</span>}
                    </p>
                    {record.historical_text && (
                      <blockquote className="archival-quote">
                        <p
                          lang={BOOK_LANG[record.entry.book]}
                        >
                          {record.historical_text}
                        </p>
                      </blockquote>
                    )}
                    <TranslateButton key={record.entry.id} text={record.historical_text} />
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
                        ["Uses and properties", record.virtues, "The author's historical account of the subject's attributed properties and uses."],
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
                              <TranslateButton text={n.quote} compact />
                            </li>
                          ))}
                        </ul>
                      ) : <p className="classification-empty">No historical names recorded.</p>}
                    </section>
                  </section>
                )}
                {(
                  <section id="sec-identification" className="record-section">
                    <p className="eyebrow">Botanical identification</p>
                    <h2 className="with-switch"><span>Candidate identifications</span>{sourceSwitch}</h2>
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
                    <label className="check-row switch-row">
                      <input
                        type="checkbox"
                        checked={showHidden}
                        onChange={(e) => setShowHidden(e.target.checked)}
                      />
                      <span>Show candidates excluded by the current criteria</span>
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
                      <div className="candidate-detail" id="candidate-detail">
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
                            <details className="detail-group" open>
                              <summary>
                                Classification &amp; geography{" "}
                                <InfoTip
                                  label="Classification and geography"
                                  text="The recorded eligibility decision, its rules, source lineages, and geographical caveats for this candidate."
                                />
                              </summary>
                              <ClassificationSummary hypothesis={currentCandidate.hypothesis} decision={currentCandidate.decision} />
                            </details>
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
                                  <Pager page={evidenceOffset / 20} hasMore={candidateDetails.has_more} onPage={(n) => setEvidenceOffset(n * 20)} label="Evidence pages" />
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
                                    <p className="section-explanation">
                                      No description comparison is linked to
                                      this candidate.
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
                                              {s.historical_quote && <div className="comparison-feature-quote"><span className="comparison-label">Historical quotation</span><blockquote>“{s.historical_quote}”</blockquote><TranslateButton text={s.historical_quote} compact /></div>}
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
                {(
                  <section id="sec-uses" className="record-section">
                    <p className="eyebrow">Historical medicinal knowledge</p>
                    <h2 className="with-switch"><span>Recorded claims</span>{sourceSwitch}</h2>
                    <p>
                      These are extracted interpretations of historical
                      statements, not evidence of medical effectiveness.
                    </p>
                    {meshClaims.length === 0 && (
                      <div className="empty">
                        No claim from this entry is mapped to a medical concept.
                      </div>
                    )}
                    {hiddenClaims > 0 && (
                      <p className="claims-hidden-note">{hiddenClaims} more claim{hiddenClaims === 1 ? "" : "s"} without a mapped medical concept {hiddenClaims === 1 ? "is" : "are"} not shown.</p>
                    )}
                    <div className="claims-list">
                      {meshClaims.map(({ claim: c, concepts }) => (
                        <button className="claim-card" key={c.id} onClick={() => openClaim(c.id)}>
                          <span className="claim-card-top">
                            <span className="claim-card-id">Claim {Number(String(c.source_claim_id).split(":").pop()?.replace(/^c/, "")) || ""}</span>
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
                {(
                  <section id="research-detail" className="research-section record-section">
                    <p className="eyebrow">Modern research</p>
                    <h2 className="with-switch">
                      <span>
                        Studies and assessments{" "}
                        <InfoTip
                          label="Studies and assessments"
                          text="Studies are connected to specific claim–plant combinations. Assessments describe relevance and limitations; they are not proof that a remedy works."
                        />
                      </span>
                      {sourceSwitch}
                    </h2>
                    <p className="section-explanation">
                      Pick a historical claim to see the plants it was checked
                      for and the modern studies assessed for it.
                    </p>
                    <div className="filter-group claim-picker">
                      <span className="filter-label">Historical claim</span>
                      <Dropdown
                        label="Historical claim"
                        value={selectedClaim || ""}
                        placeholder="Select a claim"
                        onChange={(v) => v && openClaim(v)}
                        options={meshClaims.map(({ claim: c, concepts }) => ({
                          value: c.id,
                          label: c.claim_text,
                          hint: concepts.map((x: Item) => x.name).join(", "),
                        }))}
                      />
                    </div>
                    {currentClaim && (
                      <details className="detail-group" open>
                        <summary>The historical claim</summary>
                        <blockquote className="archival-quote">
                          <p>“{currentClaim.claim.quote}”</p>
                          <TranslateButton key={currentClaim.claim.id} text={currentClaim.claim.quote} stored={currentClaim.claim.translation} />
                          <cite>
                            {claimRef(currentClaim.claim.source_claim_id, record.entry.name)}{" "}
                            <button className="cite-link" onClick={() => goTo("history")}>Read it in the historical record ↑</button>
                          </cite>
                        </blockquote>
                        <ClaimSummary claim={currentClaim.claim} concepts={currentClaim.concepts} />
                      </details>
                    )}
                    {detailLoading && <p>Loading studies…</p>}
                    {detailError && <p role="alert">{detailError}</p>}
                    {claimDetails && (
                      <>
                        <Notice>
                          <strong>Read with care</strong>
                          <p>
                            A linked study is not proof that the remedy works.
                            The assessments were made with an AI model; check how
                            closely each study matches the claim, its limitations,
                            and the original publication.
                          </p>
                        </Notice>
                        <details className="detail-group" open>
                        <summary>Which plants this claim was checked for</summary>
                        <p className="unit-intro">
                          The historical plant may correspond to more than one
                          modern species. Each is listed with how confident the
                          identification is, and whether modern studies were
                          assessed for it.
                        </p>
                        {claimDetails.units.length === 0 && (
                          <p>No modern plant is linked to this claim.</p>
                        )}
                        <ul className="unit-list">
                          {claimDetails.units.map((u: Item) => (
                            <li key={u.id}>
                              <em className="unit-plant">{value(u.candidate)}</em>
                              <span className={`unit-tier unit-tier-${u.tier}`}>{tierText(u.tier)}</span>
                              <span className="unit-status">
                                {u.assessments
                                  ? `${u.assessments} study assessment${u.assessments === 1 ? "" : "s"}`
                                  : "No studies assessed yet"}
                                {u.link_status !== "unique" &&
                                  " · the link to this plant is uncertain"}
                              </span>
                            </li>
                          ))}
                        </ul>
                        </details>
                        <details className="detail-group" open>
                        <summary>Modern studies{claimDetails.studies.length ? ` (${claimDetails.studies.length}${claimDetails.has_more ? "+" : ""})` : ""}</summary>
                        {claimDetails.studies.length === 0 && (
                          <div className="empty">
                            No modern studies have been assessed for this claim
                            yet. So far, studies were searched only for uses
                            shared across the historical texts.
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
                                <h3>
                                  {studyLink(x.study, x.source_url)
                                    ? <a className="study-title-link" href={studyLink(x.study, x.source_url)} target="_blank" rel="noreferrer">{x.study.title} <span aria-hidden="true">↗</span></a>
                                    : x.study.title}
                                </h3>
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
                                <details className="excerpts">
                                  <summary>What the study says, word for word</summary>
                                  <p className="section-explanation">
                                    Each answer the model gave is backed by an exact quotation
                                    from the study, checked against the text.
                                  </p>
                                  <dl className="excerpt-list">
                                    {x.excerpts
                                      .filter((a: Item) => a.text)
                                      .map((a: Item, i: number) => (
                                        <div key={i}>
                                          <dt>{EXCERPT_LABELS[a.field] || friendly(a.field)}</dt>
                                          <dd>“{a.text}”</dd>
                                        </div>
                                      ))}
                                  </dl>
                                  <ul className="provenance">
                                    <li><span>Study text</span>{value(x.study.text_locator)}</li>
                                    <li><span>Prompt version</span>{value(x.assessment.prompt_version)}</li>
                                    <li><span>Model reply</span>{value(x.assessment.raw_response_file)}</li>
                                  </ul>
                                </details>
                              </div>
                            </article>
                          ))}
                        </div>
                        <Pager page={studyOffset / 20} hasMore={claimDetails.has_more} onPage={(n) => setStudyOffset(n * 20)} label="Study pages" />
                        </details>
                        {claimDetails.related.length > 0 && (
                          <details className="detail-group">
                            <summary>Related records in the other book</summary>
                            <p className="section-explanation">
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
                          </details>
                        )}
                      </>
                    )}
                  </section>
                )}
                {(
                  <section id="sec-relationships" className="record-section">
                    <p className="eyebrow">Knowledge graph</p>
                    <h2 className="with-switch"><span>Explore relationships</span>{sourceSwitch}</h2>
                    <div className="switch-group">
                      <label className="check-row switch-row">
                        <input
                          type="checkbox"
                          checked={graphHidden}
                          onChange={(e) => setGraphHidden(e.target.checked)}
                        />
                        <span>Include candidates excluded by the current criteria</span>
                      </label>
                      <label className="check-row switch-row">
                        <input
                          type="checkbox"
                          checked={graphUnmapped}
                          onChange={(e) => setGraphUnmapped(e.target.checked)}
                        />
                        <span>Include claims without a medical concept (MeSH)</span>
                      </label>
                    </div>
                    <button className="primary-link map-open" onClick={() => openMap(record.entry.id)}>Open in the Knowledge Map →</button>
                    <Graph
                      key={`${graphUnmapped ? "all-claims" : "mesh-claims"}-${graphHidden ? "all" : "ab"}`}
                      record={graphUnmapped ? record : { ...record, claims: meshClaims }}
                      visible={graphHidden ? record.candidates : record.candidates.filter((x) => x.decision?.tier === "A" || x.decision?.tier === "B")}
                      openCandidate={openCandidate}
                      openClaim={openClaim}
                    />
                  </section>
                )}
                <section id="sec-review" className="record-section">
                  <p className="eyebrow">Domain experts</p>
                  <h2 className="with-switch"><span>Expert review</span>{sourceSwitch}</h2>
                  <p className="section-explanation">
                    Domain experts' confirmations, disagreements and notes on this entry's identifications, claims
                    and studies, with an agreement score for each item.
                  </p>
                  <EntryReviews entryId={record.entry.id} onAdd={() => openReview(record.entry.id)} />
                </section>
              </div>
              </div>
            </>
          )}
        </main>
      )}
      {section === "sources" && (
        <main className="standard-page sources-page">
          <div className="section-head">
            <p className="eyebrow">The collection</p>
            <h1>Historical Sources</h1>
            <p>
              Three herbals from three worlds: one in Greek for the Roman world,
              one in Chinese from Han China, and one in English for the London
              poor. Each is read here entry by entry and traced to modern plants
              and research.
            </p>
          </div>
          <ol className="source-timeline" aria-label="Timeline">
            {SOURCE_TIMELINE.map((t) => (
              <li key={t.year}><b>{t.year}</b><span>{t.text}</span></li>
            ))}
          </ol>
          {SOURCE_BOOKS.map((b) => (
            <article className="source-feature" key={b.id}>
              <header className="source-feature-head">
                <div>
                  <p className="eyebrow">{b.era}</p>
                  <h2>{b.title}</h2>
                  <p className="source-feature-sub">{b.subtitle}</p>
                </div>
                <div className="source-feature-actions">
                  <button
                    className="primary-link"
                    onClick={() => {
                      setBook(b.id)
                      setOffset(0)
                      setSearch("")
                      setTierFilter("")
                      setFamilyFilter("")
                      setConceptFilter("")
                      setResearchOnly(false)
                      setRelevantOnly(false)
                      navigate("explore")
                    }}
                  >
                    Browse its entries →
                  </button>
                  <a className="cite-link" href={b.read} target="_blank" rel="noreferrer">Read the original text ↗</a>
                </div>
              </header>
              {facets?.books?.[b.id] && (
                <dl className="source-stats">
                  <div><dt>Entries</dt><dd>{Number(facets.books[b.id].entries ?? 0).toLocaleString()}</dd></div>
                  <div><dt>With a proposed plant</dt><dd>{Number(facets.books[b.id].identified ?? 0).toLocaleString()}</dd></div>
                  <div><dt>Medicinal claims read</dt><dd>{Number(facets.books[b.id].claims ?? 0).toLocaleString()}</dd></div>
                </dl>
              )}
              <div className="source-feature-body">
                <section>
                  <h3>The author</h3>
                  {b.author.map((t, k) => <p key={k}>{t}</p>)}
                </section>
                <section>
                  <h3>The book</h3>
                  {b.book.map((t, k) => <p key={k}>{t}</p>)}
                </section>
              </div>
              <div className="source-facts">
                <p className="eyebrow">Did you know?</p>
                <ul>{b.facts.map((t, k) => <li key={k}>{t}</li>)}</ul>
              </div>
              <FeaturedEntries book={b.id} openEntry={openEntry} />
              <p className="source-edition"><span>Edition used here</span>{b.edition}</p>
            </article>
          ))}
        </main>
      )}
      {section === "about" && (
        <main className="standard-page about-page">
          <div className="section-head">
            <p className="eyebrow">About EthnoTrace</p>
            <h1>Following historical knowledge, carefully</h1>
            <p>
              Old herbals record which plants people used against which
              complaints. EthnoTrace asks a narrow question of two of them: for
              each remedy, which modern plant is the author most likely talking
              about, and what has modern research found about that plant and
              that use?
            </p>
          </div>

          <section className="about-block">
            <h2>Why it is harder than it looks</h2>
            <div className="about-columns">
              <p>
                A name in an old book is not a species. "Agrimony" in 1653 or
                εὐπατόριον in the first century may point to one plant, several,
                or one we no longer grow. The same word can name different plants
                in different places, and translators have guessed wrong for
                centuries.
              </p>
              <p>
                So every identification here is a proposal with its evidence
                attached, graded by fixed rules, and every modern study is read
                against the exact claim, not just the plant. Where the evidence is
                thin, the site says so instead of filling the gap.
              </p>
            </div>
          </section>

          <section className="about-block">
            <h2>How an entry is built</h2>
            <ol className="about-steps">
              <li>
                <span className="about-step-n">1</span>
                <div>
                  <h3>Reading the claims</h3>
                  <p>
                    Each entry's text is split into individual medicinal claims,
                    such as "eases a cough". Every claim keeps its exact quotation
                    from the book, checked against the text, and is mapped to the
                    medical vocabulary used by PubMed (MeSH).
                  </p>
                </div>
              </li>
              <li>
                <span className="about-step-n">2</span>
                <div>
                  <h3>Identifying the plant</h3>
                  <p>
                    The plant names in the entry are looked up in name databases
                    (GBIF, Wikidata, iNaturalist, ChecklistBank, NCBI Taxonomy,
                    Dr. Duke's) and, for the Greek, in the Liddell–Scott–Jones
                    lexicon. Candidates are checked against the World Flora Online
                    and Kew's plant list, against where they grow, and, where the
                    book describes the plant, against that description.
                  </p>
                </div>
              </li>
              <li>
                <span className="about-step-n">3</span>
                <div>
                  <h3>Finding the modern evidence</h3>
                  <p>
                    For uses recorded in both books, studies are gathered from
                    PubMed, Europe PMC, ClinicalTrials.gov and the European
                    Medicines Agency's herbal monographs. A language model reads
                    each study and answers fixed questions, quoting the study for
                    every answer. The verdict is then computed by written rules
                    from those answers; the model's own opinion is kept only for
                    comparison.
                  </p>
                </div>
              </li>
            </ol>
          </section>

          <section className="about-block about-grades">
            <h2>What the labels mean</h2>
            <div className="about-grade-grid">
              <div><span className="tier-pill tier-pill-A">Meets identification criteria</span><p>{tierHelp.A}</p></div>
              <div><span className="tier-pill tier-pill-B">Possible identification</span><p>{tierHelp.B}</p></div>
              <div><span className="tier-pill tier-pill-X">Excluded by current criteria</span><p>{tierHelp.X}</p></div>
            </div>
          </section>

          <section className="about-block">
            <h2>What this site does not claim</h2>
            <ul className="about-limits">
              <li>It does not say any remedy works. A linked study is evidence to read, not a recommendation.</li>
              <li>It does not prove what an ancient author meant. Even the best-supported identification is a reasoned guess.</li>
              <li>The automated steps make mistakes. Uncertain quotations and disagreements between the model and the rules are flagged so a person can check them.</li>
              <li>Nothing here is medical advice.</li>
            </ul>
          </section>

          <section className="about-block about-licences">
            <h2>Sources and licences</h2>
            <p>
              Everything on this site comes from published sources. Each one is
              credited here with its licence; individual records also link back to
              the source they came from. Because the Greek and Chinese texts and
              the Greek lexicon are CC BY-SA, material built from them is shared
              under CC BY-SA too. Licences were checked on 3–4 November 2026.
            </p>
            {(LICENCES as [string, [string, string, string][]][]).map(([group, items]) => (
              <details className="licence-group" key={group}>
                <summary>{group} <span>{items.length}</span></summary>
                <dl>
                  {items.map(([name, detail, licence]) => (
                    <div key={name}>
                      <dt>{name}{detail && <small>{detail}</small>}</dt>
                      <dd>{licence}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            ))}
          </section>

          <section className="about-block about-team">
            <h2>Who made it</h2>
            <p>
              EthnoTrace was built by team OverSlept, George Souladakis and
              Marselo Senka, for Track 1 of EthnoHack 2026. All the data
              sources are public; each record on the site links back to where it
              came from. See the Historical Sources page for the three books and
              the editions used.
            </p>
            <button className="primary-link" onClick={() => navigate("sources")}>The historical sources →</button>
          </section>
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
