/**
 * Latin-script readings of Greek and Chinese names, shown in small type under the name.
 *
 * Greek: a scholarly transliteration of ancient Greek (η = ē, ω = ō, χ = ch, rough breathing = h,
 * γγ/γκ/γξ/γχ = ng/nk/nx/nch, υ = y except in the diphthongs au, eu, ou).
 * Chinese: Hanyu Pinyin with tone marks. The traditional characters are first converted to simplified
 * (opencc-js) so that pinyin-pro can use its word list for characters with several readings; a few
 * readings can still be wrong, so the page calls it approximate. Both libraries load only when needed.
 */
import { textLanguage } from "./accessibility"

const BASE: Record<string, string> = {
  α: "a", β: "b", γ: "g", δ: "d", ε: "e", ζ: "z", η: "ē", θ: "th", ι: "i", κ: "k", λ: "l", μ: "m", ν: "n",
  ξ: "x", ο: "o", π: "p", ρ: "r", σ: "s", ς: "s", τ: "t", υ: "y", φ: "ph", χ: "ch", ψ: "ps", ω: "ō",
}
const ROUGH = "̔"      // combining reversed comma above (rough breathing)
const DIAERESIS = "̈"

function greekWord(word: string) {
  // split into base letters with their diacritics
  const letters: { base: string; marks: string; upper: boolean }[] = []
  for (const ch of word.normalize("NFD")) {
    if (/\p{M}/u.test(ch)) { if (letters.length) letters[letters.length - 1].marks += ch; continue }
    const lower = ch.toLowerCase()
    letters.push({ base: lower, marks: "", upper: lower !== ch })
  }
  let out = ""
  for (let i = 0; i < letters.length; i++) {
    const { base, marks } = letters[i]
    const next = letters[i + 1]
    const prev = letters[i - 1]
    if (!(base in BASE)) { out += base; continue }
    let t = BASE[base]
    if (base === "γ" && next && "γκξχ".includes(next.base)) t = "n"
    if (base === "υ" && prev && "αεηο".includes(prev.base) && !marks.includes(DIAERESIS)) t = "u"
    if (base === "ρ" && (i === 0 || (prev?.base === "ρ"))) t = "rh"
    // rough breathing sits on the vowel (or on the second vowel of a diphthong): h goes before the word
    const rough = marks.includes(ROUGH) || (next && "ιυ".includes(next.base) && next.marks.includes(ROUGH))
    if (rough && i <= 1 && base !== "ρ") t = (i === 0 ? "h" : "") + t
    out += t
  }
  if (out.startsWith("hh")) out = out.slice(1)
  return letters[0]?.upper ? out.charAt(0).toUpperCase() + out.slice(1) : out
}

export function romanizeGreek(text: string) {
  return text.replace(/[Ͱ-Ͽἀ-῿̀-ͯ]+/g, (w) => greekWord(w))
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chinese: Promise<(text: string) => string> | null = null
function loadChinese() {
  chinese ??= Promise.all([import("pinyin-pro"), import("opencc-js/t2cn")]).then(([py, cc]) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const toSimplified = (cc as any).Converter({ from: "t", to: "cn" })
    return (text: string) => py.pinyin(toSimplified(text), { type: "string", nonZh: "consecutive" })
  })
  return chinese
}

/** The Latin-script reading of a Greek or Chinese name, or null for anything else. */
export async function romanize(text?: string | null): Promise<{ text: string; kind: "greek" | "pinyin" } | null> {
  const lang = textLanguage(text)
  if (!text || !lang) return null
  if (lang === "el") return { text: romanizeGreek(text), kind: "greek" }
  return { text: (await loadChinese())(text), kind: "pinyin" }
}
