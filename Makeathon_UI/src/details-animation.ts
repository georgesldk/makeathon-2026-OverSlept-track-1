/**
 * Smooth open/close for every <details> dropdown in the app (2026-11-07).
 * The browser opens <details> instantly; this animates the height instead.
 * Closing from deep inside a long open list first brings its (sticky) header
 * back into view, so the page does not jump.
 */
const DURATION = 380
const EASING = "cubic-bezier(.4, 0, .2, 1)"

function closedHeight(details: HTMLDetailsElement, summary: HTMLElement) {
  const cs = getComputedStyle(details)
  const extra = ["paddingTop", "paddingBottom", "borderTopWidth", "borderBottomWidth"]
    .reduce((sum, k) => sum + (parseFloat(cs[k as keyof CSSStyleDeclaration] as string) || 0), 0)
  return summary.offsetHeight + extra
}

function run(details: HTMLDetailsElement, from: number, to: number, done: () => void) {
  details.dataset.animating = "1"
  details.style.overflow = "hidden"
  const animation = details.animate({ height: [`${from}px`, `${to}px`] }, { duration: DURATION, easing: EASING })
  const finish = () => {
    details.style.overflow = ""
    delete details.dataset.animating
    done()
  }
  animation.onfinish = finish
  animation.oncancel = finish
}

export function installDetailsAnimation() {
  document.addEventListener("click", (event) => {
    const target = event.target as Element | null
    const summary = target?.closest("summary") as HTMLElement | null
    if (!summary) return
    // links, buttons and info icons inside a summary keep their own behaviour
    if (target !== summary && target?.closest("a, button, input, select, label") && summary.contains(target.closest("a, button, input, select, label"))) return
    const details = summary.parentElement
    if (!(details instanceof HTMLDetailsElement)) return
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    event.preventDefault()
    if (details.dataset.animating) return
    const start = details.offsetHeight
    if (!details.open) {
      details.open = true
      run(details, start, details.offsetHeight, () => {})
    } else {
      // closing from far down the list: bring the top of the dropdown back first
      const top = details.getBoundingClientRect().top
      if (top < 0) window.scrollBy(0, top - 130)
      run(details, details.offsetHeight, closedHeight(details, summary), () => { details.open = false })
    }
  })
}

/** Grow (or shrink) an element smoothly from `from` px to its current height, e.g. after loaded content arrives. */
export function smoothResize(el: HTMLElement, from: number) {
  el.getAnimations().forEach((x) => x.cancel())   // an opening animation may still be running: take over from it
  const to = el.offsetHeight
  if (!from || Math.abs(to - from) < 2 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
  el.style.overflow = "hidden"
  const a = el.animate({ height: [`${from}px`, `${to}px`] }, { duration: 480, easing: EASING })
  a.onfinish = a.oncancel = () => { el.style.overflow = "" }
}

/**
 * Open dropdown headers stick just below their section's sticky title, not on top of it.
 * Each section with a sticky title gets --title-h (the title's current height); summaries use it.
 */
export function trackStickyTitles() {
  const selector = ".dash-section-title, .record-section > h2"
  const sizes = new ResizeObserver((entries) => {
    for (const e of entries) {
      const el = e.target as HTMLElement
      el.parentElement?.style.setProperty("--title-h", `${Math.ceil(el.getBoundingClientRect().height)}px`)
    }
  })
  const seen = new WeakSet<Element>()
  const scan = () => document.querySelectorAll(selector).forEach((el) => {
    if (!seen.has(el)) { seen.add(el); sizes.observe(el) }
  })
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true })
  scan()
}
