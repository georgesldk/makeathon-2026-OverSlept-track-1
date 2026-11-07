/** Decorative family-level illustrations; they do not identify an individual species. */
import type { ReactNode } from 'react'

const symbols: Record<string, ReactNode> = {
  Lamiaceae: <><path d="M16 27V8m0 13c-5 0-8-3-8-7 5 0 8 2 8 7Zm0-5c5 0 8-3 8-7-5 0-8 2-8 7Z"/><path d="M8 14c2 2 5 4 8 5m8-10c-3 2-5 4-8 5"/><circle cx="16" cy="6" r="2"/></>,
  Apiaceae: <><path d="M16 27V15M7 14l9 4 9-4M10 9l6 9 6-9M16 6v12"/><circle cx="7" cy="13" r="2"/><circle cx="10" cy="8" r="2"/><circle cx="16" cy="5" r="2"/><circle cx="22" cy="8" r="2"/><circle cx="25" cy="13" r="2"/><path d="M16 24c-3-4-6-4-8-3"/></>,
  Asteraceae: <><circle cx="16" cy="12" r="3"/><path d="M16 9c-3-5 3-5 0 0Zm3 2c4-4 7 1 0 2Zm-1 4c1 6-4 6-4 0Zm-5-2c-6 1-4-5 0-3Zm3 2v12m0-6c-4-3-6-3-8-2m8 5c3-3 5-3 7-3"/></>,
  Rosaceae: <><path d="M16 17v10m0-5c-3-4-6-4-8-3m8 5c3-3 5-3 7-3"/><path d="M16 14c-5 3-9 0-7-4-2-4 3-6 6-3 2-4 7-2 6 1 4 0 5 5 1 6-1 4-4 4-6 0Z"/><path d="M13 11c1-2 5-2 6 0-1 2-4 2-6 0Z"/></>,
  Fabaceae: <><path d="M7 24C8 13 14 7 25 6c-1 11-7 17-18 18Z"/><path d="M7 24 24 7"/><circle cx="13" cy="18" r="1.5"/><circle cx="17" cy="14" r="1.5"/><circle cx="21" cy="10" r="1.5"/></>,
  Brassicaceae: <><path d="M16 16v11m0-5c-3-3-6-3-8-2m8 4c3-3 5-4 8-4"/><circle cx="16" cy="10" r="2"/><path d="M16 8c-4-5 4-5 0 0Zm2 2c5-4 5 4 0 0Zm-2 2c4 5-4 5 0 0Zm-2-2c-5 4-5-4 0 0Z"/></>,
  Ranunculaceae: <><path d="M16 17v10m0-4c-3-3-6-3-8-2"/><circle cx="16" cy="10" r="2"/><path d="M16 8c-3-4 1-6 2-2m0 3c4-4 7 0 2 2m-2 1c4 3 0 6-2 2m-2-1c-3 4-6 0-2-2m1-2c-5-1-3-5 1-4"/></>,
  Solanaceae: <><path d="M16 16v11m0-5c-3-3-6-3-8-2m8 4c3-3 6-4 8-4"/><path d="m16 4 2 5 5-1-3 4 3 4-5-1-2 5-2-5-5 1 3-4-3-4 5 1z"/><circle cx="16" cy="12" r="1.4"/></>,
  Poaceae: <><path d="M16 27V5m0 6c-4 0-6-2-6-5 4 0 6 2 6 5Zm0 4c4 0 6-2 6-5-4 0-6 2-6 5Zm0 4c-4 0-6-2-6-5 4 0 6 2 6 5Zm0 4c4 0 6-2 6-5-4 0-6 2-6 5ZM12 27l4-4 4 4"/></>,
  bulb: <><path d="M16 15V5m0 10c-3-6-5-8-8-9 1 5 3 9 6 11m2-2c3-6 5-8 8-9-1 5-3 9-6 11"/><path d="M16 14c-1 4-6 4-6 9 0 3 2 4 6 4s6-1 6-4c0-5-5-5-6-9Z"/><path d="m12 27-2 2m6-2v2m4-2 2 2"/></>,
  cone: <><path d="M16 5c-3 2-7 7-7 12 0 6 3 10 7 10s7-4 7-10c0-5-4-10-7-12Z"/><path d="m11 11 5 3 5-3m-11 5 6 4 6-4m-11 5 5 3 5-3M16 5V2"/></>,
  Malvaceae: <><path d="M16 18v9m0-4c-3-4-6-4-8-3"/><path d="M16 8c-3-5-7-2-5 2-5-1-5 4 0 4-2 5 3 6 5 2 2 4 7 3 5-2 5 0 5-5 0-4 2-4-2-7-5-2Z"/><path d="M16 12v-4m-2 4h4"/><circle cx="16" cy="12" r="1.5"/></>,
  fallback: <><path d="M7 25C7 15 13 8 25 7c-1 12-8 18-18 18Z"/><path d="M7 25 20 12"/></>,
}
const aliases: Record<string,string> = { Liliaceae: 'bulb', Amaryllidaceae: 'bulb', Pinaceae: 'cone', Cupressaceae: 'cone' }

export function familyIconKey(family?: string | null): string {
  const name = (family || '').trim()
  return aliases[name] || (Object.prototype.hasOwnProperty.call(symbols, name) ? name : 'fallback')
}

export default function FamilyIcon({ family, className }: { family?: string | null; className?: string }) {
  return <svg viewBox="0 0 32 32" width="32" height="32" className={className} data-family-icon={familyIconKey(family)} aria-hidden="true" focusable="false">
    <circle cx="16" cy="16" r="15.5" fill="#e2ecdf" />
    <g fill="none" stroke="#173f2b" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round">{symbols[familyIconKey(family)]}</g>
  </svg>
}
