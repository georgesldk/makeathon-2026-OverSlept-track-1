import { useMemo, useState } from "react"

type Page = "explore" | "overview" | "history" | "identification" | "uses" | "studies" | "relationships" | "sources" | "about"
type Drawer = { type: "source" | "study" | "claim"; title: string } | null

const botanicalImages = [
  "https://images.unsplash.com/photo-1633081528845-1c0b71d8a010?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1727525895897-a27e75899aba?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1726923152884-dfb9203d3b4d?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1574087274792-b82d8d1e7094?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1726921301160-1ba081052faf?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1584284621253-09ff82142b6f?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1726921300230-80e735c71fc7?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1726923153023-3cc61adf9284?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1584282000482-9da6ab6ada34?auto=format&fit=crop&w=700&q=85",
  "https://images.unsplash.com/photo-1748715712942-462315782b64?auto=format&fit=crop&w=700&q=85",
]

const plants = [
  {
    name: "Chickweed",
    scientific: "Stellaria media",
    source: "Culpeper",
    status: "B — Possible",
    use: "Skin & wounds",
    family: "Caryophyllaceae",
    research: true,
  },
  {
    name: "Rosemary",
    scientific: "Salvia rosmarinus",
    source: "Culpeper",
    status: "A — Shown",
    use: "Pain & inflammation",
    family: "Lamiaceae",
    research: true,
  },
  {
    name: "Yarrow",
    scientific: "Achillea millefolium",
    source: "Dioscorides",
    status: "A — Shown",
    use: "Skin & wounds",
    family: "Asteraceae",
    research: true,
  },
  {
    name: "Garlic",
    scientific: "Allium sativum",
    source: "Dioscorides",
    status: "A — Shown",
    use: "Digestive",
    family: "Amaryllidaceae",
    research: true,
  },
  {
    name: "Amara Dulcis",
    scientific: "Solanum dulcamara",
    source: "Culpeper",
    status: "B — Possible",
    use: "Skin & wounds",
    family: "Solanaceae",
    research: false,
  },
  {
    name: "Plantain",
    scientific: "Plantago major",
    source: "Culpeper",
    status: "B — Possible",
    use: "Respiratory",
    family: "Plantaginaceae",
    research: true,
  },
  {
    name: "Mandrake",
    scientific: "Mandragora officinarum",
    source: "Dioscorides",
    status: "B — Possible",
    use: "Pain & inflammation",
    family: "Solanaceae",
    research: true,
  },
  {
    name: "Moonwort",
    scientific: "No accepted candidate",
    source: "Culpeper",
    status: "Unresolved",
    use: "Skin & wounds",
    family: "Unresolved",
    research: false,
  },
  {
    name: "Marsh Mallow",
    scientific: "Althaea officinalis",
    source: "Dioscorides",
    status: "A — Shown",
    use: "Respiratory",
    family: "Malvaceae",
    research: true,
  },
  {
    name: "Rue",
    scientific: "Ruta graveolens",
    source: "Culpeper",
    status: "B — Possible",
    use: "Digestive",
    family: "Rutaceae",
    research: false,
  },
]

const navItems = [
  ["Explore", "explore"],
  ["Historical Sources", "sources"],
  ["About", "about"],
] as [string, Page][]

const recordTabs = [
  ["Overview", "overview"],
  ["Historical Record", "history"],
  ["Identification", "identification"],
  ["Relationships", "relationships"],
] as [string, Page][]

function Icon({
  name,
}: {
  name: "search" | "grid" | "list" | "external" | "arrow" | "close" | "back"
}) {
  const paths = {
    search: (
      <>
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    grid: (
      <>
        <rect x="4" y="4" width="6" height="6" />
        <rect x="14" y="4" width="6" height="6" />
        <rect x="4" y="14" width="6" height="6" />
        <rect x="14" y="14" width="6" height="6" />
      </>
    ),
    list: (
      <>
        <path d="M8 6h12M8 12h12M8 18h12" />
        <circle cx="4" cy="6" r=".7" fill="currentColor" />
        <circle cx="4" cy="12" r=".7" fill="currentColor" />
        <circle cx="4" cy="18" r=".7" fill="currentColor" />
      </>
    ),
    external: (
      <>
        <path d="M14 4h6v6M20 4l-9 9" />
        <path d="M18 13v6H5V6h6" />
      </>
    ),
    arrow: <path d="m9 5 7 7-7 7" />,
    close: <path d="m5 5 14 14M19 5 5 19" />,
    back: <path d="m15 5-7 7 7 7" />,
  }
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function SourceLink({
  children,
  onClick,
}: {
  children: React.ReactNode
  onClick: () => void
}) {
  return (
    <button className="source-link" onClick={onClick}>
      {children}
      <Icon name="external" />
    </button>
  )
}

function App() {
  const [page, setPage] = useState<Page>("explore")
  const [selectedPlant, setSelectedPlant] = useState("Chickweed")
  const [query, setQuery] = useState("")
  const [view, setView] = useState<"grid" | "list">("grid")
  const [sourceFilter, setSourceFilter] = useState("All sources")
  const [statusFilter, setStatusFilter] = useState("All statuses")
  const [useFilter, setUseFilter] = useState("All uses")
  const [familyFilter, setFamilyFilter] = useState("All families")
  const [researchOnly, setResearchOnly] = useState(false)
  const [candidate, setCandidate] = useState(0)
  const [drawer, setDrawer] = useState<Drawer>(null)
  const [mobileNav, setMobileNav] = useState(false)

  const go = (next: Page) => {
    setPage(next)
    setMobileNav(false)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  const filteredPlants = useMemo(
    () =>
      plants.filter(
        (p) =>
          (p.name.toLowerCase().includes(query.toLowerCase()) ||
            p.scientific.toLowerCase().includes(query.toLowerCase())) &&
          (sourceFilter === "All sources" || p.source === sourceFilter) &&
          (statusFilter === "All statuses" || p.status === statusFilter) &&
          (useFilter === "All uses" || p.use === useFilter) &&
          (familyFilter === "All families" || p.family === familyFilter) &&
          (!researchOnly || p.research),
      ),
    [query, sourceFilter, statusFilter, useFilter, familyFilter, researchOnly],
  )

  const openPlant = (name: string) => {
    setSelectedPlant(name)
    setCandidate(0)
    go("overview")
  }

  const isRecord = [
    "overview",
    "history",
    "identification",
    "uses",
    "studies",
    "relationships",
  ].includes(page)

  return (
    <div className="app-shell">
      <header className="site-header">
        <button
          className="brand"
          onClick={() => go("explore")}
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
          {navItems.map(([label, target]) => (
            <button
              key={target}
              className={
                page === target || (label === "Explore" && isRecord)
                  ? "active"
                  : ""
              }
              onClick={() => go(target)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      {isRecord ? (
        <RecordShell
          page={page}
          go={go}
          drawer={drawer}
          setDrawer={setDrawer}
          candidate={candidate}
          setCandidate={setCandidate}
          selectedPlant={selectedPlant}
        />
      ) : page === "explore" ? (
        <ExplorePage
          filteredPlants={filteredPlants}
          query={query}
          setQuery={setQuery}
          view={view}
          setView={setView}
          sourceFilter={sourceFilter}
          setSourceFilter={setSourceFilter}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          useFilter={useFilter}
          setUseFilter={setUseFilter}
          familyFilter={familyFilter}
          setFamilyFilter={setFamilyFilter}
          researchOnly={researchOnly}
          setResearchOnly={setResearchOnly}
          openPlant={openPlant}
        />
      ) : page === "sources" ? (
        <SourcesPage setDrawer={setDrawer} browseSource={(source) => { setSourceFilter(source); setStatusFilter("All statuses"); setUseFilter("All uses"); setFamilyFilter("All families"); setResearchOnly(false); setQuery(""); go("explore") }} />
      ) : (
        <AboutPage go={go} />
      )}

      <footer>
        <div className="footer-brand">EthnoTrace</div>
        <p>
          A prototype for source-led historical botanical research.
          Demonstration records are clearly marked.
        </p>
        <button onClick={() => go("about")}>About this prototype</button>
      </footer>
      {drawer && (
        <EvidenceDrawer drawer={drawer} close={() => setDrawer(null)} />
      )}
    </div>
  )
}

function Breadcrumbs({
  page,
  go,
  plantName,
}: {
  page: Page
  go: (p: Page) => void
  plantName: string
}) {
  const label: Record<string, string> = {
    overview: "Overview",
    history: "Historical Record",
    identification: "Identification",
    uses: "Medicinal Uses",
    studies: "Studies",
    relationships: "Relationships",
  }
  return (
    <div className="breadcrumbs">
      <button onClick={() => go("explore")}>Explore</button>
      <span>/</span>
      <button onClick={() => go("overview")}>{plantName}</button>
      {page !== "overview" && (
        <>
          <span>/</span>
          <span>{label[page]}</span>
        </>
      )}
    </div>
  )
}

function ExplorePage(props: {
  filteredPlants: typeof plants
  query: string
  setQuery: (v: string) => void
  view: "grid" | "list"
  setView: (v: "grid" | "list") => void
  sourceFilter: string
  setSourceFilter: (v: string) => void
  statusFilter: string
  setStatusFilter: (v: string) => void
  useFilter: string
  setUseFilter: (v: string) => void
  familyFilter: string
  setFamilyFilter: (v: string) => void
  researchOnly: boolean
  setResearchOnly: (v: boolean) => void
  openPlant: (name: string) => void
}) {
  const {
    filteredPlants,
    query,
    setQuery,
    view,
    setView,
    sourceFilter,
    setSourceFilter,
    statusFilter,
    setStatusFilter,
    useFilter,
    setUseFilter,
    familyFilter,
    setFamilyFilter,
    researchOnly,
    setResearchOnly,
    openPlant,
  } = props
  const [browseMode, setBrowseMode] = useState("By plant")
  const displayedPlants = [...filteredPlants].sort((a, b) => {
    if (browseMode === "By historical source")
      return a.source.localeCompare(b.source)
    if (browseMode === "By medicinal use") return a.use.localeCompare(b.use)
    if (browseMode === "By scientific species")
      return a.scientific.localeCompare(b.scientific)
    if (browseMode === "By research evidence")
      return Number(b.research) - Number(a.research)
    return a.name.localeCompare(b.name)
  })
  const clear = () => {
    setQuery("")
    setSourceFilter("All sources")
    setStatusFilter("All statuses")
    setUseFilter("All uses")
    setFamilyFilter("All families")
    setResearchOnly(false)
  }
  return (
    <main>
      <section className="catalog-intro">
        <p className="eyebrow">Explore the collection</p>
        <h1>Historical plants, traced to the present</h1>
        <p>
          Browse plant records from early herbals and examine their proposed
          connections to modern taxonomy and scientific research.
        </p>
        <div className="browse-modes">
          {[
            "By plant",
            "By historical source",
            "By medicinal use",
            "By scientific species",
            "By research evidence",
          ].map((x) => (
            <button
              className={browseMode === x ? "active" : ""}
              key={x}
              onClick={() => setBrowseMode(x)}
            >
              {x}
            </button>
          ))}
        </div>
      </section>
      <div className="catalog-layout">
        <aside className="filters">
          <div className="filter-heading">
            <h2>Refine</h2>
            <button onClick={clear}>Clear all</button>
          </div>
          <FilterSelect
            label="Historical source"
            value={sourceFilter}
            onChange={setSourceFilter}
            options={["All sources", "Culpeper", "Dioscorides"]}
          />
          <FilterSelect
            label="Identification status"
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              "All statuses",
              "A — Shown",
              "B — Possible",
              "Unresolved",
            ]}
          />
          <FilterSelect
            label="Medicinal use"
            value={useFilter}
            onChange={setUseFilter}
            options={[
              "All uses",
              "Skin & wounds",
              "Digestive",
              "Respiratory",
              "Pain & inflammation",
            ]}
          />
          <FilterSelect
            label="Scientific family"
            value={familyFilter}
            onChange={setFamilyFilter}
            options={[
              "All families",
              "Asteraceae",
              "Caryophyllaceae",
              "Lamiaceae",
              "Solanaceae",
            ]}
          />
          <label className="check-row">
            <input
              type="checkbox"
              checked={researchOnly}
              onChange={(e) => setResearchOnly(e.target.checked)}
            />
            <span>Modern research available</span>
          </label>
        </aside>
        <section className="catalog">
          <div className="catalog-tools">
            <label className="search">
              <Icon name="search" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search historical or scientific names"
                aria-label="Search historical or scientific names"
              />
            </label>
            <div className="view-toggle" aria-label="View options">
              <button
                aria-pressed={view === "grid"}
                className={view === "grid" ? "active" : ""}
                onClick={() => setView("grid")}
                aria-label="Grid view"
              >
                <Icon name="grid" />
              </button>
              <button
                aria-pressed={view === "list"}
                className={view === "list" ? "active" : ""}
                onClick={() => setView("list")}
                aria-label="List view"
              >
                <Icon name="list" />
              </button>
            </div>
          </div>
          <div className="results-note">
            <span>
              Showing {filteredPlants.length} demonstration records ·{" "}
              {browseMode.toLowerCase()}
            </span>
            <span>Illustrative imagery · not species records</span>
          </div>
          <div className={`plant-collection ${view}`}>
            {displayedPlants.map((plant) => (
              <button
                key={plant.name}
                className="plant-card"
                onClick={() => openPlant(plant.name)}
              >
                <div className="plant-image">
                  <img
                    src={botanicalImages[plants.indexOf(plant) % botanicalImages.length]}
                    alt=""
                  />
                </div>
                <div className="plant-card-copy">
                  <span className="record-source">{plant.source}</span>
                  <h3>{plant.name}</h3>
                  <em>{plant.scientific}</em>
                  <span
                    className={`status ${plant.status.startsWith("A") ? "shown" : plant.status.startsWith("B") ? "possible" : "unresolved"}`}
                  >
                    {plant.status}
                  </span>
                </div>
              </button>
            ))}
          </div>
          {filteredPlants.length === 0 && (
            <div className="empty">
              <h3>No matching records</h3>
              <p>Try broadening the search or clearing one or more filters.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
}) {
  return (
    <label className="filter-group">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  )
}

function RecordShell({
  page,
  go,
  drawer,
  setDrawer,
  candidate,
  setCandidate,
  selectedPlant,
}: {
  page: Page
  go: (p: Page) => void
  drawer: Drawer
  setDrawer: (d: Drawer) => void
  candidate: number
  setCandidate: (n: number) => void
  selectedPlant: string
}) {
  const plant = plants.find((item) => item.name === selectedPlant) ?? plants[0]
  const plantImage =
    botanicalImages[plants.indexOf(plant) % botanicalImages.length]
  const isChickweed = plant.name === "Chickweed"
  return (
    <main className="record-main">
      <button className="record-back" onClick={() => go("explore")}>
        <Icon name="back" /> Back to results
      </button>
      <Breadcrumbs page={page} go={go} plantName={plant.name} />
      <section className="record-hero">
        <div className="record-plate">
          <img
            src={plantImage}
            alt=""
          />
          <span>Illustrative image</span>
        </div>
        <div className="record-heading">
          <p className="eyebrow">Historical plant record · {plant.source}</p>
          <h1>{plant.name}</h1>
          <div className="identity-line">
            <span>Candidate identity</span>
            <em>{plant.scientific}</em>
            <span
              className={`status ${plant.status.startsWith("A") ? "shown" : plant.status.startsWith("B") ? "possible" : "unresolved"}`}
            >
              {plant.status}
            </span>
          </div>
          <p>
            Recorded in{" "}
            {plant.source === "Culpeper" ? (
              <cite>The Complete Herbal</cite>
            ) : (
              <cite>De materia medica</cite>
            )}
            . The proposed modern identification remains subject to evidence
            review.
          </p>
          <SourceLink
            onClick={() =>
              setDrawer({
                type: "source",
                title: `${plant.source} — historical source record`,
              })
            }
          >
            Inspect source record
          </SourceLink>
        </div>
      </section>
      <nav className="record-tabs" aria-label={`${plant.name} record sections`}>
        {recordTabs.map(([label, target]) => (
          <button
            key={target}
            className={page === target ? "active" : ""}
            onClick={() => go(target)}
          >
            {label}
          </button>
        ))}
      </nav>
      {!isChickweed && (
        <GenericRecord
          plant={plant}
          page={page}
          go={go}
          setDrawer={setDrawer}
        />
      )}
      {isChickweed && page === "overview" && (
        <Overview go={go} setDrawer={setDrawer} />
      )}
      {isChickweed && page === "history" && (
        <Historical setDrawer={setDrawer} />
      )}
      {isChickweed && page === "identification" && (
        <Identification
          candidate={candidate}
          setCandidate={setCandidate}
          setDrawer={setDrawer}
        />
      )}
      {isChickweed && page === "uses" && <Uses setDrawer={setDrawer} />}
      {isChickweed && page === "studies" && <Studies setDrawer={setDrawer} />}
      {isChickweed && page === "relationships" && <Relationships go={go} />}
    </main>
  )
}

function SectionHead({
  kicker,
  title,
  copy,
}: {
  kicker: string
  title: string
  copy: string
}) {
  return (
    <div className="section-head">
      <p className="eyebrow">{kicker}</p>
      <h2>{title}</h2>
      <p>{copy}</p>
    </div>
  )
}

function GenericRecord({
  plant,
  page,
  go,
  setDrawer,
}: {
  plant: typeof plants[number]
  page: Page
  go: (p: Page) => void
  setDrawer: (d: Drawer) => void
}) {
  const sectionNames: Partial<Record<Page, string>> = {
    overview: "Record overview",
    history: "Historical record",
    identification: "Botanical identification",
    uses: "Medicinal uses",
    studies: "Modern scientific evidence",
    relationships: "Relationships",
  }
  return (
    <div className="record-content overview-grid">
      <section className="overview-intro">
        <SectionHead
          kicker="Catalog record"
          title={`${sectionNames[page]} for ${plant.name}`}
          copy={`This demonstration record preserves the selected plant across research views. Its source is ${plant.source}, and its current identification state is ${plant.status.toLowerCase()}.`}
        />
        <div className="notice">
          <strong>Prototype scope</strong>
          <p>
            Detailed evidence has been fully modeled for Chickweed. This catalog
            entry intentionally avoids inventing quotations, identifiers, or
            study results where verified records have not been supplied.
          </p>
        </div>
        <div className="pathways">
          <button onClick={() => go("identification")}>
            <span>
              <strong>Review identification state</strong>
              <small>
                {plant.scientific} · {plant.status}
              </small>
            </span>
            <Icon name="arrow" />
          </button>
          <button
            onClick={() =>
              setDrawer({
                type: "source",
                title: `${plant.source} — ${plant.name}`,
              })
            }
          >
            <span>
              <strong>Inspect source status</strong>
              <small>See what is and is not verified for this record.</small>
            </span>
            <Icon name="arrow" />
          </button>
        </div>
      </section>
      <aside className="record-facts">
        <h3>Record fields</h3>
        <dl>
          <dt>Historical name</dt>
          <dd>{plant.name}</dd>
          <dt>Candidate identity</dt>
          <dd>
            <em>{plant.scientific}</em>
          </dd>
          <dt>Historical source</dt>
          <dd>{plant.source}</dd>
          <dt>Scientific family</dt>
          <dd>{plant.family}</dd>
          <dt>Research availability</dt>
          <dd>
            {plant.research
              ? "Illustrative modern records available"
              : "No modern records attached"}
          </dd>
        </dl>
      </aside>
    </div>
  )
}

function Overview({
  go,
  setDrawer,
}: {
  go: (p: Page) => void
  setDrawer: (d: Drawer) => void
}) {
  return (
    <div className="record-content overview-grid">
      <section className="overview-intro">
        <SectionHead
          kicker="Record overview"
          title="A historical record, with two possible identities"
          copy="Culpeper’s Chickweed record describes a low-growing herb associated with damp ground and several medicinal preparations. EthnoTrace links this historical entry to two modern botanical candidates while keeping the evidence and uncertainty visible."
        />
        <div className="notice">
          <strong>Research note</strong>
          <p>
            This prototype uses illustrative summaries and placeholder research
            records. No medical or identification claim on this page should be
            treated as verified.
          </p>
        </div>
        <h3>Research pathways</h3>
        <div className="pathways">
          {[
            [
              "Read the historical record",
              "Names, habitat, seasonal notes, and attributed uses.",
              "history",
            ],
            [
              "Review candidate identities",
              "Compare name, taxonomy, geography, and morphology.",
              "identification",
            ],
            [
              "Examine medicinal claims",
              "See the recorded preparations in historical context.",
              "uses",
            ],
            [
              "Compare modern evidence",
              "Assess how contemporary studies relate to the record.",
              "studies",
            ],
          ].map(([title, copy, target]) => (
            <button onClick={() => go(target as Page)} key={title}>
              <span>
                <strong>{title}</strong>
                <small>{copy}</small>
              </span>
              <Icon name="arrow" />
            </button>
          ))}
        </div>
      </section>
      <aside className="record-facts">
        <h3>At a glance</h3>
        <dl>
          <dt>Historical source</dt>
          <dd>
            Culpeper, <cite>The Complete Herbal</cite>
          </dd>
          <dt>Name recorded</dt>
          <dd>Chickweed</dd>
          <dt>Leading candidate</dt>
          <dd>
            <em>Stellaria media</em>
          </dd>
          <dt>Alternative candidate</dt>
          <dd>
            <em>Cerastium fontanum</em>
          </dd>
          <dt>Review state</dt>
          <dd>Awaiting specialist review</dd>
        </dl>
        <SourceLink
          onClick={() =>
            setDrawer({ type: "source", title: "Source record and citation" })
          }
        >
          View citation details
        </SourceLink>
      </aside>
    </div>
  )
}

function Historical({ setDrawer }: { setDrawer: (d: Drawer) => void }) {
  return (
    <div className="record-content reading-width">
      <SectionHead
        kicker="Historical record"
        title="The Chickweed entry in Culpeper"
        copy="This transcription workspace separates source metadata from interpretive summaries. Text shown below is demonstrative and is not represented as a verified quotation."
      />
      <div className="aliases">
        <span>Recorded name</span>
        <strong>Chickweed</strong>
        <span>Index aliases</span>
        <strong>Common chickweed · Starweed</strong>
      </div>
      <h3>Botanical description</h3>
      <p className="body-copy">
        A low herb of cultivated and disturbed ground, described through its
        slender stems, small paired leaves, and pale star-like flowers. This is
        an illustrative modern paraphrase for prototype purposes, not a
        historical transcription.
      </p>
      <div className="archival-quote">
        <span>Archival excerpt · transcription withheld</span>
        <p>
          “Verified source text would be displayed here after comparison against
          a named edition or page image.”
        </p>
        <small>Prototype placeholder — not an original quotation</small>
      </div>
      <div className="two-columns">
        <div>
          <h3>Habitat</h3>
          <p className="body-copy">
            Associated in the record with damp, cultivated ground and places
            near habitation.
          </p>
        </div>
        <div>
          <h3>Season</h3>
          <p className="body-copy">
            Described as available across an extended growing period. Exact
            phrasing requires source verification.
          </p>
        </div>
      </div>
      <h3>Attributed medicinal passages</h3>
      <p className="body-copy">
        The entry associates the plant with topical preparations and cooling
        applications. See Medicinal Uses for structured, clearly qualified
        claims.
      </p>
      <div className="citation-block">
        <div>
          <span>Source citation</span>
          <strong>
            Nicholas Culpeper, <cite>The Complete Herbal</cite>
          </strong>
          <small>
            Edition and passage location: placeholder pending bibliographic
            verification
          </small>
        </div>
        <SourceLink
          onClick={() =>
            setDrawer({ type: "source", title: "Historical source details" })
          }
        >
          View source
        </SourceLink>
      </div>
    </div>
  )
}

const candidates = [
  {
    name: "Stellaria media",
    family: "Caryophyllaceae",
    status: "A — Shown",
    taxon: "Accepted name",
    geo: "Compatible",
    review: "Specialist review pending",
  },
  {
    name: "Cerastium fontanum",
    family: "Caryophyllaceae",
    status: "B — Possible",
    taxon: "Accepted name",
    geo: "Compatible",
    review: "Specialist review pending",
  },
]

function Identification({
  candidate,
  setCandidate,
  setDrawer,
}: {
  candidate: number
  setCandidate: (n: number) => void
  setDrawer: (d: Drawer) => void
}) {
  const c = candidates[candidate]
  return (
    <div className="record-content">
      <SectionHead
        kicker="Botanical identification"
        title="Compare modern candidate species"
        copy="A — Shown meets the illustrative eligibility criteria; B — Possible remains plausible with uncertainties. X — Hidden candidates are excluded from main results but retained in the data. Categories are not probabilities of correctness. Both candidates await specialist review."
      />
      <div className="candidate-layout">
        <aside className="candidate-list" aria-label="Candidate species">
          {candidates.map((item, i) => (
            <button
              key={item.name}
              className={candidate === i ? "selected" : ""}
              onClick={() => setCandidate(i)}
            >
              <span>{item.status}</span>
              <em>{item.name}</em>
              <small>{item.family}</small>
              <b>{candidate === i ? "Selected" : "Review candidate"}</b>
            </button>
          ))}
        </aside>
        <section className="candidate-detail">
          <div className="candidate-title">
            <div>
              <span>Candidate {candidate + 1}</span>
              <h2>
                <em>{c.name}</em>
              </h2>
              <p>{c.family}</p>
            </div>
            <span className="status provisional">{c.status}</span>
          </div>
          <div className="evidence-summary">
            {[
              ["Name match", candidate === 0 ? "Strong" : "Partial"],
              ["Taxonomic status", c.taxon],
              ["Geography", c.geo],
              ["Human review", "Pending"],
            ].map(([a, b]) => (
              <div key={a}>
                <span>{a}</span>
                <strong>{b}</strong>
              </div>
            ))}
          </div>
          <EvidenceSection title="Name evidence" defaultOpen>
            <dl className="evidence-dl">
              <dt>Historical name</dt>
              <dd>Chickweed</dd>
              <dt>Illustrative dataset name</dt>
              <dd>
                {candidate === 0 ? "common chickweed" : "mouse-ear chickweed"}
              </dd>
              <dt>Dataset</dt>
              <dd>GBIF name index — illustrative link</dd>
              <dt>Record identifier</dt>
              <dd>Placeholder identifier, not a live taxon record</dd>
            </dl>
            <SourceLink
              onClick={() =>
                setDrawer({ type: "source", title: "Botanical name evidence" })
              }
            >
              Inspect name evidence
            </SourceLink>
          </EvidenceSection>
          <EvidenceSection title="Taxonomic information">
            <dl className="evidence-dl">
              <dt>Proposed accepted name</dt>
              <dd>
                <em>{c.name}</em>
              </dd>
              <dt>Synonyms</dt>
              <dd>
                Illustrative synonymy withheld pending record verification
              </dd>
              <dt>References</dt>
              <dd>WFO and WCVP comparison proposed</dd>
              <dt>Disagreements</dt>
              <dd>No disagreement recorded in prototype data</dd>
            </dl>
          </EvidenceSection>
          <EvidenceSection title="Geographical assessment">
            <p>
              Both candidates occur in Britain and are compatible with the broad
              context of Culpeper’s work. This does not, by itself, resolve the
              identification.
            </p>
          </EvidenceSection>
          <EvidenceSection title="Botanical description comparison">
            <div className="comparison-table">
              <div className="table-head">
                <span>Trait</span>
                <span>Historical text</span>
                <span>Modern description</span>
                <span>Assessment</span>
              </div>
              {[
                [
                  "Growth habit",
                  "Low, spreading herb",
                  candidate === 0 ? "Low annual herb" : "Low perennial herb",
                  "Match",
                ],
                [
                  "Flowers",
                  "Small and star-like",
                  candidate === 0
                    ? "White, deeply divided petals"
                    : "White, notched petals",
                  candidate === 0 ? "Match" : "Partial match",
                ],
                [
                  "Stem",
                  "Slender",
                  candidate === 0 ? "Single line of hairs" : "Hairy throughout",
                  candidate === 0 ? "Partial match" : "Contradiction",
                ],
                [
                  "Leaf form",
                  "Small paired leaves",
                  "Opposite simple leaves",
                  "Match",
                ],
              ].map((row) => (
                <div className="table-row" key={row[0]}>
                  {row.map((cell, i) => (
                    <span
                      key={i}
                      className={
                        i === 3
                          ? `assessment ${cell.toLowerCase().replace(" ", "-")}`
                          : ""
                      }
                    >
                      {cell}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </EvidenceSection>
          <details className="ai-assessment"><summary>Illustrative automated assessment</summary>
            <div className="ai-label">Automated description comparison</div>
            <h3>
              Suggested assessment:{" "}
              {candidate === 0 ? "broadly compatible" : "mixed evidence"}
            </h3>
            <p>
              This method compares structured descriptive traits. It does not
              establish the historical identity.
            </p>
            <div className="ai-columns">
              <div>
                <strong>Features that agree</strong>
                <ul>
                  <li>Low growth habit</li>
                  <li>Opposite leaves</li>
                  <li>White, divided flowers</li>
                </ul>
              </div>
              <div>
                <strong>Contradictions or gaps</strong>
                <ul>
                  <li>Stem hair detail is incomplete</li>
                  <li>No fruit description</li>
                  <li>Seasonal language unverified</li>
                </ul>
              </div>
            </div>
            <div className="method">
              <span>Method</span>
              <b>Illustrative AI-assisted trait comparison · no model connected</b>
              <span>Result</span>
              <b>
                {candidate === 0
                  ? "3 of 4 comparable traits agree"
                  : "2 of 4 comparable traits agree"}
              </b>
              <span>Human review</span>
              <b>Not yet reviewed</b>
            </div>
          </details>
        </section>
      </div>
    </div>
  )
}

function EvidenceSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details className="evidence-section" open={defaultOpen}>
      <summary>
        {title}
        <span>+</span>
      </summary>
      <div>{children}</div>
    </details>
  )
}

const claims = [
  {
    category: "Skin and wounds",
    condition: "Topical cooling application",
    part: "Whole herb",
    preparation: "Fresh plant preparation",
    administration: "External",
    relation: "Related but indirect",
  },
  {
    category: "Pain and inflammation",
    condition: "Swelling and discomfort",
    part: "Aerial parts",
    preparation: "Illustrative poultice",
    administration: "External",
    relation: "Insufficient evidence",
  },
  {
    category: "Respiratory conditions",
    condition: "General chest complaint",
    part: "Unspecified",
    preparation: "Unverified historical preparation",
    administration: "Unclear",
    relation: "Insufficient evidence",
  },
]

function Uses({ setDrawer }: { setDrawer: (d: Drawer) => void }) {
  return (
    <div className="record-content">
      <SectionHead
        kicker="Medicinal uses"
        title="Historical claims in context"
        copy="These records describe attributed historical uses, not medical advice or established clinical effects. Quoted text is withheld where a verified transcription is not available."
      />
      <div className="warning-line">
        <strong>Historical evidence only</strong>
        <span>
          Do not use this information to diagnose, treat, or prepare remedies.
        </span>
      </div>
      <div className="claims-list">
        {claims.map((claim, i) => (
          <button
            key={claim.condition}
            onClick={() => setDrawer({ type: "claim", title: claim.condition })}
          >
            <span className="claim-index">0{i + 1}</span>
            <div>
              <span>{claim.category}</span>
              <h3>{claim.condition}</h3>
              <p>
                {claim.part} · {claim.preparation} · {claim.administration}
              </p>
            </div>
            <span className="claim-action">
              View claim <Icon name="arrow" />
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

const studies = [
  {
    type: "In-vitro study",
    year: "2021",
    title:
      "Illustrative screening of Stellaria media extracts in an experimental assay",
    source: "Demonstration record · no verified publication attached",
    species: "Stellaria media",
    outcome:
      "A laboratory response was reported in the illustrative dataset; methods and result require source verification.",
    relation: "Related but indirect",
  },
  {
    type: "Chemical study",
    year: "2019",
    title: "Illustrative phytochemical profile of aerial plant material",
    source: "Demonstration record · no verified DOI",
    species: "Stellaria media",
    outcome:
      "Several compound classes are listed for interface demonstration only.",
    relation: "Insufficient evidence",
  },
  {
    type: "Review",
    year: "2023",
    title:
      "Historical uses and modern investigation of common chickweed: a narrative overview",
    source: "Placeholder bibliographic record",
    species: "Stellaria media",
    outcome:
      "Summarizes heterogeneous preclinical literature without establishing clinical effectiveness.",
    relation: "Partially comparable",
  },
]

function Studies({ setDrawer }: { setDrawer: (d: Drawer) => void }) {
  const [type, setType] = useState("All study types")
  const shown =
    type === "All study types"
      ? studies
      : studies.filter((s) => s.type === type)
  return (
    <div className="record-content">
      <SectionHead
        kicker="Modern scientific evidence"
        title="How modern research relates to the historical claim"
        copy="Study records below are illustrative placeholders, not verified publications. Relationship labels describe comparability—not whether a historical claim has been proven."
      />
      <div className="study-toolbar">
        <div className="legend">
          <span>Historical claim</span>
          <i />
          <span>Relationship assessment</span>
          <i />
          <span>Modern evidence</span>
        </div>
        <FilterSelect
          label="Filter studies"
          value={type}
          onChange={setType}
          options={[
            "All study types",
            "In-vitro study",
            "Chemical study",
            "Review",
          ]}
        />
      </div>
      <div className="claim-comparison">
        <div>
          <span>Historical claim</span>
          <h3>External preparation for swelling and skin discomfort</h3>
          <button
            onClick={() =>
              setDrawer({ type: "claim", title: "Historical claim details" })
            }
          >
            Expand historical passage
          </button>
        </div>
        <div className="relationship">
          <span>Related but indirect</span>
          <p>
            The plant and broad biological process overlap, but the preparation,
            dosage, and studied outcome are not directly comparable.
          </p>
        </div>
        <div>
          <span>Evidence landscape</span>
          <h3>Preclinical and chemical records only</h3>
          <p>No verified clinical study is included in this prototype.</p>
        </div>
      </div>
      <div className="study-list">
        {shown.map((study) => (
          <article key={study.title}>
            <div className="study-meta">
              <span>{study.type}</span>
              <span>{study.year}</span>
            </div>
            <div className="study-body">
              <h3>{study.title}</h3>
              <p className="citation">{study.source}</p>
              <dl>
                <dt>Species studied</dt>
                <dd>
                  <em>{study.species}</em>
                </dd>
                <dt>Reported outcome</dt>
                <dd>{study.outcome}</dd>
                <dt>Relationship</dt>
                <dd>
                  <span className="relation-label">{study.relation}</span>
                </dd>
              </dl>
            </div>
            <button
              className="text-button"
              onClick={() => setDrawer({ type: "study", title: study.title })}
            >
              View study details <Icon name="arrow" />
            </button>
          </article>
        ))}
      </div>
    </div>
  )
}

function Relationships({ go }: { go: (p: Page) => void }) {
  const [mode, setMode] = useState<"Graph" | "List" | "Timeline">("Graph")
  const [visible, setVisible] = useState({
    sources: true,
    species: true,
    uses: true,
    studies: true,
  })
  const toggle = (key: keyof typeof visible) =>
    setVisible({ ...visible, [key]: !visible[key] })
  const groups = [
    {
      key: "sources",
      label: "Historical Sources",
      item: "The Complete Herbal",
      page: "history",
    },
    {
      key: "species",
      label: "Candidate Species",
      item: "Stellaria media",
      page: "identification",
    },
    {
      key: "uses",
      label: "Medicinal Uses",
      item: "Skin & wounds",
      page: "uses",
    },
    {
      key: "studies",
      label: "Modern Studies",
      item: "3 illustrative records",
      page: "studies",
    },
  ] as const
  return (
    <div className="record-content">
      <SectionHead
        kicker="Relationships"
        title="Connected records for Chickweed"
        copy="Explore illustrative connections from this record. Select a relationship to inspect its context and evidence."
      />
      <div className="relationship-tools">
        <div className="mode-switch">
          {(["Graph", "List", "Timeline"] as const).map((x) => (
            <button
              className={mode === x ? "active" : ""}
              onClick={() => setMode(x)}
              key={x}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="category-toggles">
          {groups.map((g) => (
            <label key={g.key}>
              <input
                checked={visible[g.key]}
                onChange={() => toggle(g.key)}
                type="checkbox"
              />
              {g.label}
            </label>
          ))}
        </div>
      </div>
      {mode === "Graph" ? (
        <div className="graph">
          <div className="center-node">
            <span>Historical plant</span>
            <strong>Chickweed</strong>
            <small>Culpeper</small>
          </div>
          {groups
            .filter((g) => visible[g.key])
            .map((g, i) => (
              <button
                className={`graph-node node-${i}`}
                key={g.key}
                onClick={() => go(g.page)}
              >
                <span>{g.label}</span>
                <strong>{g.item}</strong>
                <small>
                  {g.key === "species" ? "Proposed link" : "Illustrative link"}
                </small>
              </button>
            ))}
        </div>
      ) : mode === "List" ? (
        <div className="relationship-list">
          {groups
            .filter((g) => visible[g.key])
            .map((g) => (
              <button key={g.key} onClick={() => go(g.page)}>
                <span>{g.label}</span>
                <strong>{g.item}</strong>
                <Icon name="arrow" />
              </button>
            ))}
        </div>
      ) : (
        <div className="timeline">
          <div>
            <span>1653</span>
            <strong>Culpeper’s herbal published</strong>
          </div>
          <div>
            <span>Illustrative present</span>
            <strong>Candidate species linked</strong>
          </div>
          <div>
            <span>Pending</span>
            <strong>Specialist review</strong>
          </div>
        </div>
      )}
    </div>
  )
}

function SourcesPage({ setDrawer, browseSource }: { setDrawer: (d: Drawer) => void; browseSource: (source: string) => void }) {
  return (
    <main className="standard-page">
      <div className="breadcrumbs">
        <span>Historical Sources</span>
      </div>
      <SectionHead
        kicker="The archive"
        title="Historical works and research sources"
        copy="EthnoTrace distinguishes primary historical works, botanical authorities, and modern literature indexes. Every record should remain inspectable at the point of use."
      />
      <div className="source-browse"><span>Browse historical records</span><button onClick={() => browseSource("Culpeper")}>Culpeper records →</button><button onClick={() => browseSource("Dioscorides")}>Dioscorides records →</button></div>
      <div className="source-library">
        {[
          [
            "Nicholas Culpeper",
            "The Complete Herbal",
            "English herbal · historical source",
          ],
          [
            "Dioscorides",
            "De materia medica",
            "Wellmann edition · historical source",
          ],
          [
            "World Flora Online",
            "Taxonomic treatments",
            "Modern botanical authority",
          ],
          [
            "WCVP",
            "Nomenclature and distribution",
            "Modern botanical authority",
          ],
          ["GBIF", "Taxon records", "Biodiversity data index"],
          [
            "PubMed / Europe PMC",
            "Scientific publications",
            "Literature indexes",
          ],
        ].map(([a, b, c]) => (
          <button
            key={b}
            onClick={() => setDrawer({ type: "source", title: `${a} — ${b}` })}
          >
            <span>{c}</span>
            <h3>{b}</h3>
            <p>{a}</p>
            <b>
              View source information <Icon name="external" />
            </b>
          </button>
        ))}
      </div>
    </main>
  )
}

function AboutPage({ go }: { go: (p: Page) => void }) {
  return (
    <main className="standard-page about-page">
      <div className="breadcrumbs">
        <span>About</span>
      </div>
      <SectionHead
        kicker="About EthnoTrace"
        title="A transparent bridge between historical texts and modern plant science"
        copy="EthnoTrace is conceived as a research environment for historians, botanists, digital humanities scholars, and students. It keeps evidence, interpretation, and uncertainty visibly separate."
      />
      <div className="about-grid">
        <div>
          <h3>Research principles</h3>
          <ul>
            <li>Historical claims remain in their original medical context.</li>
            <li>
              Modern identities are candidates, not automatic equivalences.
            </li>
            <li>Every assertion should point to inspectable evidence.</li>
            <li>Automated methods suggest comparisons; people review them.</li>
          </ul>
        </div>
        <div>
          <h3>Prototype data</h3>
          <p>
            This interface uses demonstration records. Historical paraphrases,
            publication summaries, record identifiers, and automated comparisons
            are explicitly illustrative unless marked as verified.
          </p>
          <button className="primary-button" onClick={() => go("explore")}>
            Explore the collection
          </button>
        </div>
      </div>
    </main>
  )
}

function EvidenceDrawer({
  drawer,
  close,
}: {
  drawer: NonNullable<Drawer>
  close: () => void
}) {
  return (
    <div
      className="drawer-wrap"
      role="dialog"
      aria-modal="true"
      aria-label={drawer.title}
    >
      <button
        className="drawer-backdrop"
        onClick={close}
        aria-label="Close panel"
      />
      <aside className="drawer">
        <div className="drawer-head">
          <span>
            {drawer.type === "study"
              ? "Study record"
              : drawer.type === "claim"
                ? "Claim evidence"
                : "Source information"}
          </span>
          <button onClick={close} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
        <h2>{drawer.title}</h2>
        {drawer.type === "source" && (
          <>
            <p className="drawer-lead">
              This panel is the reusable inspection point for citation details,
              dataset versions, and external records.
            </p>
            <dl>
              <dt>Record type</dt>
              <dd>Demonstration source record</dd>
              <dt>Citation status</dt>
              <dd>Bibliographic details require verification</dd>
              <dt>Edition / dataset</dt>
              <dd>Not specified in prototype data</dd>
              <dt>External identifier</dt>
              <dd>No live identifier attached</dd>
            </dl>
            <div className="drawer-note">
              <strong>Source transparency</strong>
              <p>
                No mock URL is presented as a real scientific record. A
                production record would link to the named archive or dataset.
              </p>
            </div>
          </>
        )}
        {drawer.type === "study" && (
          <>
            <p className="drawer-lead">
              Illustrative publication data for interface evaluation only.
            </p>
            <dl>
              <dt>Study type</dt>
              <dd>{studies.find((study) => study.title === drawer.title)?.type ?? "Illustrative record"}</dd>
              <dt>Plant studied</dt>
              <dd>
                <em>Stellaria media</em>
              </dd>
              <dt>Plant part</dt>
              <dd>Aerial material</dd>
              <dt>Identifier</dt>
              <dd>Placeholder — no DOI or PMID supplied</dd>
              <dt>Relationship</dt>
              <dd>{studies.find((study) => study.title === drawer.title)?.relation ?? "Illustrative relationship"}</dd>
            </dl>
            <div className="drawer-note">
              <strong>Why this classification?</strong>
              <p>
                The species overlaps with the proposed historical identity, but
                preparation and measured outcomes do not reproduce the
                historical claim.
              </p>
            </div>
          </>
        )}
        {drawer.type === "claim" && (
          <>
            <p className="drawer-lead">
              A structured historical-use record, separated from modern
              evidence.
            </p>
            <dl>
              <dt>Condition or symptom</dt>
              <dd>Swelling and skin discomfort</dd>
              <dt>Plant part</dt>
              <dd>Aerial parts</dd>
              <dt>Preparation</dt>
              <dd>Topical preparation, details unverified</dd>
              <dt>Administration</dt>
              <dd>External</dd>
              <dt>Historical source</dt>
              <dd>
                Culpeper, <cite>The Complete Herbal</cite>
              </dd>
            </dl>
            <div className="archival-quote compact">
              <span>Original passage</span>
              <p>Verified transcription not supplied for this prototype.</p>
              <small>No invented quotation displayed</small>
            </div>
          </>
        )}
        <button className="secondary-button" onClick={close}>
          <Icon name="back" /> Return to record
        </button>
      </aside>
    </div>
  )
}

export default App
