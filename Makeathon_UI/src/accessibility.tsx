import { useEffect, useRef, useState } from "react"
import { useOutside } from "./controls"

/* ---------- Display: light/dark theme and colour vision palettes ---------- */
// The palettes themselves are generated into themes.css by scripts/make_themes.py.

type Theme = "system" | "light" | "dark"
type Vision = "standard" | "contrast" | "cvd"
const KEY = "ethnotrace-display"

function readDisplay(): { theme: Theme; vision: Vision } {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "{}")
    return { theme: ["light", "dark"].includes(v.theme) ? v.theme : "system", vision: ["contrast", "cvd"].includes(v.vision) ? v.vision : "standard" }
  } catch { return { theme: "system", vision: "standard" } }
}

const prefersDark = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches

/** Sets data-theme and data-vision on <html>; call once before the first render to avoid a flash. */
export function applyDisplay(d = readDisplay()) {
  const root = document.documentElement
  root.dataset.theme = d.theme === "system" ? (prefersDark() ? "dark" : "light") : d.theme
  if (d.vision === "standard") delete root.dataset.vision; else root.dataset.vision = d.vision
}

export function DisplayMenu() {
  const [d, setD] = useState(readDisplay)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useOutside(box, () => setOpen(false), open)
  useEffect(() => {
    applyDisplay(d)
    try { localStorage.setItem(KEY, JSON.stringify(d)) } catch { /* private window */ }
    if (d.theme !== "system") return
    const mq = matchMedia("(prefers-color-scheme: dark)")
    const on = () => applyDisplay(d)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [d])
  const group = <K extends "theme" | "vision">(key: K, label: string, options: [typeof d[K], string, string?][]) => (
    <fieldset className="display-group">
      <legend>{label}</legend>
      {options.map(([value, text, hint]) => (
        <label key={value} className={d[key] === value ? "on" : ""}>
          <input type="radio" name={key} checked={d[key] === value} onChange={() => setD({ ...d, [key]: value })} />
          <span>{text}{hint && <small>{hint}</small>}</span>
        </label>
      ))}
    </fieldset>
  )
  return (
    <div className="display-menu" ref={box}>
      <button type="button" className="display-button" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(!open)}
        title="Display settings: dark mode, high contrast, colour-blind safe colours">
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M8 1.5a6.5 6.5 0 0 1 0 13Z" fill="currentColor" /></svg><span className="display-button-text">Display</span>
      </button>
      {open && (
        <div className="display-popover" role="dialog" aria-label="Display settings">
          {group("theme", "Theme", [["system", "Match my device"], ["light", "Light"], ["dark", "Dark"]])}
          {group("vision", "Colours", [["standard", "Standard"], ["contrast", "High contrast", "Darker text and borders"],
            ["cvd", "Colour-blind safe", "Red–green safe: greens shown as blue, reds as orange"]])}
        </div>
      )}
    </div>
  )
}

/* ---------- Voice search (Web Speech API) ---------- */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Recognition: any = typeof window !== "undefined" && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

export function VoiceButton({ onText }: { onText: (text: string) => void }) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState("")
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rec = useRef<any>(null)
  useEffect(() => () => rec.current?.abort(), [])
  if (!Recognition) return null
  const start = () => {
    if (listening) return rec.current?.stop()
    const r = new Recognition()
    r.lang = "en-GB"; r.interimResults = true; r.maxAlternatives = 1
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    r.onresult = (e: any) => onText(Array.from(e.results).map((x: any) => x[0].transcript).join("").trim())
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    r.onerror = (e: any) => setError(e.error === "not-allowed" || e.error === "service-not-allowed" ? "Microphone access was blocked." : e.error === "no-speech" ? "No speech heard; try again." : "Voice search failed.")
    r.onend = () => setListening(false)
    setError(""); setListening(true); rec.current = r; r.start()
  }
  return (
    <>
      <button type="button" className={`voice-button${listening ? " listening" : ""}`} onClick={start} aria-pressed={listening}
        aria-label={listening ? "Stop voice search" : "Search by voice"} title={error || (listening ? "Listening… click to stop" : "Search by voice")}>
        <svg viewBox="0 0 24 24" aria-hidden="true" width="16" height="16"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0M12 17v4m-3 0h6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
      </button>
      {(listening || error) && <span className="voice-status" role="status">{listening ? "Listening…" : error}</span>}
    </>
  )
}

/* ---------- Translate to English on click ---------- */

/** The language of a passage, from its script: Greek or Chinese, otherwise null (treated as English). */
export function textLanguage(text?: string | null): "el" | "zh" | null {
  if (!text) return null
  const greek = (text.match(/[Ͱ-Ͽἀ-῿]/g) || []).length
  const han = (text.match(/[㐀-鿿豈-﫿]/g) || []).length
  if (han >= 2 && han >= greek) return "zh"
  if (greek >= 3) return "el"
  return null
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const translators: Record<string, Promise<any>> = {}

async function browserTranslate(text: string, lang: "el" | "zh", onProgress: (p: number) => void) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const T = (self as any).Translator
  if (!T) throw new Error("no-api")
  if (!translators[lang]) {
    const availability = await T.availability({ sourceLanguage: lang, targetLanguage: "en" })
    if (availability === "unavailable") throw new Error("no-pair")
    translators[lang] = T.create({
      sourceLanguage: lang, targetLanguage: "en",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      monitor(m: any) { m.addEventListener("downloadprogress", (e: any) => onProgress(e.loaded)) },
    }).catch((err: unknown) => { delete translators[lang]; throw err })
  }
  const t = await translators[lang]
  const parts = text.split(/(\n+)/)
  const out = []
  for (const p of parts) out.push(p.trim() ? await t.translate(p) : p)
  return out.join("")
}

/**
 * A "Translate to English" button for a Greek or Chinese passage. Renders nothing for English text.
 * `stored` is a translation that already exists in the data (claim quotes, translated in Stage 1);
 * otherwise the browser's built-in translator is used (Chrome 138 or later).
 */
export function TranslateButton({ text, stored, compact }: { text?: string | null; stored?: string | null; compact?: boolean }) {
  const lang = textLanguage(text)
  const [state, setState] = useState<{ open: boolean; busy: boolean; result?: string; error?: string; progress?: number }>({ open: false, busy: false })
  if (!lang || !text) return null
  const source = lang === "el" ? "Greek" : "Chinese"
  const toggle = async () => {
    if (state.open) return setState({ ...state, open: false })
    if (stored || state.result) return setState({ ...state, open: true })
    setState({ open: true, busy: true })
    try {
      const result = await browserTranslate(text, lang, (p) => setState((s) => ({ ...s, progress: p })))
      setState({ open: true, busy: false, result })
    } catch (e) {
      const code = e instanceof Error ? e.message : ""
      setState({ open: true, busy: false, error: code === "no-api"
        ? "This browser has no built-in translator. It needs Chrome 138 or later on a computer."
        : code === "no-pair" ? `The browser's translator does not offer ${source} to English.` : "The translation failed. Try again." })
    }
  }
  return (
    <div className={`translate${compact ? " compact" : ""}`}>
      <button type="button" className="translate-button" aria-expanded={state.open} onClick={toggle}>
        <span aria-hidden="true">文A</span> {state.open ? "Hide English translation" : "Translate to English"}
      </button>
      {state.open && (
        <div className="translate-result" lang="en">
          {state.busy ? <p>{state.progress !== undefined && state.progress < 1 ? `Downloading the ${source} translator… ${Math.round(state.progress * 100)}%` : "Translating…"}</p>
            : state.error ? <p className="translate-error">{state.error}</p>
            : <p>{stored || state.result}</p>}
          {!state.busy && !state.error && (
            <small>{stored ? "Translated by the AI model that extracted the claims (Stage 1); not checked by an expert."
              : lang === "el" ? "Machine translation by your browser. It reads the text as modern Greek, so Ancient Greek terms may be wrong; not checked by an expert."
              : "Machine translation by your browser. Classical Chinese may be translated loosely; not checked by an expert."}</small>
          )}
        </div>
      )}
    </div>
  )
}
