/**
 * Atlas (2026-11-07): a draggable globe. Each book sits where it was written; click it and its plants
 * open around it as bubbles. Click a plant to light up where it grows natively (WCVP, WGSRPD level 2)
 * next to the author's home, which is the geography rule (A5) made visible.
 * Data: /atlas/regions.topo.json (TDWG WGSRPD level-2 outlines, simplified) and
 * /atlas/plant_ranges.json (export_atlas_ranges.py). Entries come from the read-only API.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { geoGraticule10, geoOrthographic, geoPath, geoCentroid, geoDistance, type GeoPermissibleObjects } from "d3-geo"
import { feature } from "topojson-client"
import type { Topology, GeometryCollection } from "topojson-specification"
import FamilyIcon from "./FamilyIcon"

type Item = Record<string, any>
type Region = { type: "Feature"; properties: { LEVEL2_NAM: string }; geometry: GeoPermissibleObjects }

const BOOKS = [
  { id: "culpeper", name: "Culpeper", place: "London", year: "1652–53", coords: [-0.13, 51.51] as [number, number] },
  { id: "dioscorides", name: "Dioscorides", place: "Anazarbus, Cilicia", year: "c. AD 77", coords: [35.9, 37.26] as [number, number] },
]
const SIZE = 640
const MAX_BUBBLES = 60      // plants shown around the book once a family is open
const MAX_FAMILIES = 30     // family bubbles shown when a book is opened
const NO_FAMILY = "Family not recorded"
const GOLDEN = Math.PI * (3 - Math.sqrt(5))   // sunflower spiral: each bubble turns by the golden angle

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Could not load ${url}`)
  return r.json()
}

export default function Atlas({ openEntry }: { openEntry: (id: string) => void }) {
  const [regions, setRegions] = useState<Region[]>([])
  const [ranges, setRanges] = useState<Record<string, string[]>>({})
  const [families, setFamilies] = useState<Record<string, string>>({})
  const [family, setFamily] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const svgRef = useRef<SVGSVGElement>(null)
  const [rotation, setRotation] = useState<[number, number]>([-15, -38])
  const [book, setBook] = useState<string | null>(null)
  const [plants, setPlants] = useState<Item[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [selected, setSelected] = useState<Item | null>(null)
  const [hover, setHover] = useState<Item | null>(null)
  const [failedImages, setFailedImages] = useState<Set<string>>(() => new Set())
  const [query, setQuery] = useState("")
  const drag = useRef<{ x: number; y: number; r: [number, number] } | null>(null)
  const anim = useRef(0)

  useEffect(() => {
    getJson<Topology>("/atlas/regions.topo.json")
      .then((t) => setRegions((feature(t, t.objects.level2 as GeometryCollection) as unknown as { features: Region[] }).features))
      .catch((e) => setError(e.message))
    getJson<{ ranges: Record<string, string[]>; families?: Record<string, string> }>("/atlas/plant_ranges.json")
      .then((d) => { setRanges(d.ranges); setFamilies(d.families || {}) }).catch(() => setRanges({}))
  }, [])
  // zoom with the mouse wheel (a non-passive listener, so the page itself does not scroll)
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      setZoom((z) => Math.min(6, Math.max(1, z * (e.deltaY < 0 ? 1.12 : 1 / 1.12))))
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [])

  const projection = useMemo(() => geoOrthographic().scale((SIZE / 2 - 8) * zoom).translate([SIZE / 2, SIZE / 2]).rotate(rotation).clipAngle(90), [rotation, zoom])
  const path = useMemo(() => geoPath(projection), [projection])
  const highlighted = useMemo(() => new Set(selected ? ranges[selected.preferred_scientific_name] || [] : []), [selected, ranges])

  // spin smoothly so a point faces the viewer
  const spinTo = (lon: number, lat: number) => {
    cancelAnimationFrame(anim.current)
    const from = rotation, to: [number, number] = [-lon, -lat]
    let dl = to[0] - from[0]
    dl = ((dl + 540) % 360) - 180
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 900), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
      setRotation([from[0] + dl * e, from[1] + (to[1] - from[1]) * e])
      if (t < 1) anim.current = requestAnimationFrame(step)
    }
    anim.current = requestAnimationFrame(step)
  }

  const openBook = async (id: string) => {
    const b = BOOKS.find((x) => x.id === id)!
    setBook(id); setSelected(null); setPlants([]); setQuery(""); setError(""); setFamily(null)
    spinTo(b.coords[0] + 25, b.coords[1] - 8)
    setLoading(true)
    try {
      const all: Item[] = []
      for (let offset = 0; offset < 2000; offset += 50) {
        const page = await getJson<{ items: Item[]; has_more: boolean }>(`/api/entries?identified=1&book=${id}&limit=50&offset=${offset}`)
        all.push(...page.items)
        if (!page.has_more) break
      }
      // identified (A) first, then those with a photo
      all.sort((a, b) => Number((b.tiers || []).includes("A")) - Number((a.tiers || []).includes("A")) || Number(!!b.image) - Number(!!a.image))
      setPlants(all)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const pick = (p: Item) => {
    setSelected(p)
    const names = ranges[p.preferred_scientific_name] || []
    const shapes = regions.filter((r) => names.includes(r.properties.LEVEL2_NAM))
    if (shapes.length) {
      const [lon, lat] = geoCentroid({ type: "FeatureCollection", features: shapes } as unknown as GeoPermissibleObjects)
      spinTo(lon, lat)
    }
  }

  // bubbles: a sunflower spiral around the open book's marker, in screen space
  const current = BOOKS.find((b) => b.id === book)
  const marker = current ? projection(current.coords) : null
  const markerVisible = current ? geoDistance(current.coords, [-rotation[0], -rotation[1]]) < Math.PI / 2 : false
  const famOf = (p: Item) => families[p.preferred_scientific_name] || NO_FAMILY
  const groups = useMemo(() => {
    const m = new Map<string, Item[]>()
    for (const p of plants) m.set(famOf(p), [...(m.get(famOf(p)) || []), p])
    return [...m.entries()].sort((a, b) => (a[0] === NO_FAMILY ? 1 : b[0] === NO_FAMILY ? -1 : b[1].length - a[1].length))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plants, families])
  const spiral = (i: number, start: number, step: number) => {
    const r = start + step * Math.sqrt(i + 1), a = i * GOLDEN
    return { x: (marker?.[0] || 0) + r * Math.cos(a), y: (marker?.[1] || 0) + r * Math.sin(a) }
  }
  const familyBubbles = family || selected ? [] : groups.slice(0, MAX_FAMILIES).map(([name, items], i) => ({
    name, count: items.length, r: Math.min(33, 18 + 3 * Math.sqrt(items.length)), ...spiral(i, 66, 40),
  }))
  const familyPlants = family ? groups.find(([n]) => n === family)?.[1] || [] : []
  const bubbles = selected
    ? [{ p: selected, ...spiral(0, 56, 20) }]
    : familyPlants.slice(0, MAX_BUBBLES).map((p, i) => ({ p, ...spiral(i, 56, 20) }))
  const list = (family ? familyPlants : plants).filter((p) => !query || `${p.name} ${p.preferred_scientific_name}`.toLowerCase().includes(query.toLowerCase()))

  const onDown = (e: React.PointerEvent) => {
    if ((e.target as Element).closest(".atlas-bubble, .atlas-book, .atlas-family")) return
    cancelAnimationFrame(anim.current)
    drag.current = { x: e.clientX, y: e.clientY, r: rotation }
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return
    const k = 0.35
    const lat = Math.max(-80, Math.min(80, drag.current.r[1] - (e.clientY - drag.current.y) * k))
    setRotation([drag.current.r[0] + (e.clientX - drag.current.x) * k, lat])
  }
  const onUp = () => { drag.current = null }

  return (
    <main className="atlas-page">
      <div className="section-head atlas-head">
        <p className="eyebrow">Atlas</p>
        <h1>Where the plants grow</h1>
        <p>
          Explore locations associated with each historical author and the modern native range of each
          proposed plant identification. Modern distributions provide context; they do not establish
          where a plant grew historically or prove an identification. Drag the globe to turn it.
        </p>
      </div>
      <div className="atlas-layout">
        <div className="atlas-stage">
          <svg ref={svgRef} viewBox={`0 0 ${SIZE} ${SIZE}`} className="atlas-globe" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp} role="img" aria-label="Globe with the historical books and the native ranges of their plants">
            <defs>
              <radialGradient id="atlas-sea" cx="40%" cy="35%" r="70%">
                <stop offset="0%" stopColor="#fbfaf5" />
                <stop offset="100%" stopColor="#e9e6da" />
              </radialGradient>
              {bubbles.map(({ p }) => <clipPath id={`clip-${p.id}`} key={p.id}><circle r="16" /></clipPath>)}
            </defs>
            <path d={path({ type: "Sphere" }) || ""} fill="url(#atlas-sea)" stroke="#bfc8bb" />
            <path d={path(geoGraticule10()) || ""} fill="none" stroke="#d8d5c9" strokeWidth="0.6" />
            {regions.map((r) => (
              <path key={r.properties.LEVEL2_NAM} d={path(r.geometry) || ""}
                className={`atlas-region${highlighted.has(r.properties.LEVEL2_NAM) ? " native" : ""}`}>
                <title>{r.properties.LEVEL2_NAM}</title>
              </path>
            ))}
            {markerVisible && bubbles.map(({ p, x, y }, i) => (
              <g key={p.id} className={`atlas-bubble${selected?.id === p.id ? " selected" : ""}`} transform={`translate(${x},${y})`}
                style={{ animationDelay: `${Math.min(i, 60) * 12}ms` }}
                onClick={() => pick(p)} onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}
                role="button" aria-label={p.preferred_scientific_name}>
                <circle r="18" className="atlas-bubble-ring" />
                {p.image?.image_url && !failedImages.has(p.image.image_url)
                  ? <image href={p.image.image_url} x="-16" y="-16" width="32" height="32" preserveAspectRatio="xMidYMid slice" clipPath={`url(#clip-${p.id})`} onError={() => setFailedImages(previous => new Set(previous).add(p.image.image_url))} />
                  : <g transform="translate(-16,-16)"><FamilyIcon family={famOf(p)} /></g>}
              </g>
            ))}
            {markerVisible && familyBubbles.map((f, i) => (
              <g key={f.name} className="atlas-family" transform={`translate(${f.x},${f.y})`} style={{ animationDelay: `${i * 18}ms` }}
                onClick={() => { setFamily(f.name); setQuery("") }} onMouseEnter={() => setHover({ family: f.name, count: f.count })} onMouseLeave={() => setHover(null)}
                role="button" aria-label={`${f.name}, ${f.count} plants`}>
                <circle r={f.r} className="atlas-family-dot" />
                <text y="5" textAnchor="middle" className="atlas-family-count">{f.count}</text>
                <text y={f.r + 13} textAnchor="middle" className="atlas-family-label">{f.name === NO_FAMILY ? "Other" : f.name}</text>
              </g>
            ))}
            {BOOKS.map((b) => {
              const xy = projection(b.coords)
              const visible = geoDistance(b.coords, [-rotation[0], -rotation[1]]) < Math.PI / 2
              if (!xy || !visible) return null
              return (
                <g key={b.id} className={`atlas-book${book === b.id ? " open" : ""}`} transform={`translate(${xy[0]},${xy[1]})`}
                  onClick={() => (book === b.id ? setBook(null) : openBook(b.id))} role="button" aria-label={`${b.name}, ${b.place}`}>
                  <circle r="32" className="atlas-book-halo" />
                  <circle r="21" className="atlas-book-dot" />
                  <text y="6" textAnchor="middle">{b.name[0]}</text>
                  <text y="46" textAnchor="middle" className="atlas-book-label">{b.name}</text>
                </g>
              )
            })}
            {hover && !hover.family && (() => {
              const b = bubbles.find((x) => x.p.id === hover.id)
              return b ? (
                <text x={b.x} y={b.y - 26} textAnchor="middle" className="atlas-bubble-name">
                  <tspan className="sci">{hover.preferred_scientific_name}</tspan>
                  {hover.name && <tspan x={b.x} dy="15">{hover.name}</tspan>}
                </text>
              ) : null
            })()}
          </svg>
          {hover?.family && <div className="atlas-hover"><em>{hover.family}</em><span>{hover.count} plant{hover.count === 1 ? "" : "s"} · click to open</span></div>}
          <div className="atlas-zoom">
            <button type="button" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(6, z * 1.4))}>+</button>
            <button type="button" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(1, z / 1.4))}>−</button>
            <button type="button" aria-label="Reset view" onClick={() => setZoom(1)}>⟲</button>
          </div>
          <div className="atlas-legend">
            <span><i className="dot book" /> Location associated with the author</span>
            <span><i className="dot native" /> Native range of the selected plant</span>
            <span>Family icons are illustrations, not species photographs.</span>
          </div>
        </div>

        <aside className="atlas-panel">
          {!book && (
            <>
              <p className="eyebrow">Choose a book</p>
              {BOOKS.map((b) => (
                <button key={b.id} className="atlas-book-card" onClick={() => openBook(b.id)}>
                  <strong>{b.name}</strong><span>{b.place} · {b.year}</span>
                </button>
              ))}
              <p className="atlas-note">Or click a book's marker on the globe.</p>
            </>
          )}
          {book && current && (
            <>
              <button className="cite-link" onClick={() => { setBook(null); setSelected(null); setFamily(null) }}>‹ All books</button>
              <h2>{current.name}</h2>
              <p className="atlas-note">{current.place} · {current.year}</p>
              {loading && <p className="atlas-note">Loading its plants…</p>}
              {error && <p role="alert">{error}</p>}
              {selected && (
                <div className="atlas-plant">
                  <div className="atlas-plant-photo">{selected.image?.image_url && !failedImages.has(selected.image.image_url) ? <img src={selected.image.image_url} alt="" onError={() => setFailedImages(previous => new Set(previous).add(selected.image.image_url))} /> : <FamilyIcon family={famOf(selected)} />}</div>
                  {selected.image?.image_url && !failedImages.has(selected.image.image_url) && <p className="atlas-image-credit">Photo of proposed candidate · {selected.image.creator} · <a href={selected.image.license_url} target="_blank" rel="noreferrer">Licence</a> · <a href={selected.image.image_source_url || selected.image.occurrence_url} target="_blank" rel="noreferrer">Source</a></p>}
                  <em>{selected.preferred_scientific_name}</em>
                  <span>{selected.name}{selected.chapter ? ` · ${selected.chapter}` : ""}</span>
                  <p className="atlas-range">
                    {(ranges[selected.preferred_scientific_name] || []).length
                      ? <>Native in: {(ranges[selected.preferred_scientific_name] || []).join(", ")}.</>
                      : "No native range recorded for this name."}
                  </p>
                  <button className="primary-link" onClick={() => openEntry(selected.id)}>Open the plant page →</button>
                  <button className="cite-link atlas-back-bubbles" onClick={() => setSelected(null)}>‹ Back to the {family ? "family's plants" : "families"}</button>
                </div>
              )}
              {!!plants.length && !family && !query && (
                <>
                  <p className="eyebrow atlas-sub">{groups.length} plant families · {plants.length} plants</p>
                  <ul className="atlas-list atlas-families">
                    {groups.map(([name, items]) => (
                      <li key={name}><button onClick={() => setFamily(name)}><em>{name}</em><span>{items.length}</span></button></li>
                    ))}
                  </ul>
                  <p className="atlas-note">Or search all its plants:</p>
                </>
              )}
              {!!plants.length && family && (
                <>
                  <button className="cite-link" onClick={() => { setFamily(null); setQuery("") }}>‹ All families</button>
                  <p className="eyebrow atlas-sub">{family} · {familyPlants.length} plants</p>
                </>
              )}
              {!!plants.length && (
                <>
                  <input className="atlas-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={family ? `Search ${familyPlants.length} plants` : `Search all ${plants.length} plants`} />
                  {family && familyPlants.length > MAX_BUBBLES && <p className="atlas-note">The globe shows the first {MAX_BUBBLES}; every plant is in this list.</p>}
                  {(family || query) && <ul className="atlas-list">
                    {list.map((p) => (
                      <li key={p.id}><button className={selected?.id === p.id ? "active" : ""} onClick={() => pick(p)}>
                        <em>{p.preferred_scientific_name}</em><span>{p.name || p.chapter}</span>
                      </button></li>
                    ))}
                  </ul>}
                </>
              )}
            </>
          )}
        </aside>
      </div>
    </main>
  )
}
