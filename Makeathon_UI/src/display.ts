/** Plain-language labels for recorded classifications, not new assessments. */
const labels: Record<string, string> = {
  A: 'Meets identification criteria', B: 'Possible identification', X: 'Excluded by current criteria',
  direct: 'Close match to the historical claim', partial: 'Some similarities to the historical claim',
  indirect: 'Indirect connection', not_relevant: 'Not relevant to this claim', unassessable: 'Not enough information to compare',
  same: 'Recorded as matching', related: 'Related', different: 'Different', unknown: 'Not recorded', unclear: 'Unclear',
  human_rct: 'Randomized study in people', human_other: 'Study in people', systematic_review: 'Systematic review',
  registered_trial: 'Registered trial', animal: 'Animal study', in_vivo: 'Animal study', in_vitro: 'Laboratory study (cells or tissue)',
  regulatory_monograph: 'Regulatory monograph', traditional_use_document: 'Traditional-use document', other: 'Other source',
  positive: 'Positive result reported', negative: 'Negative result reported', mixed: 'Mixed results', inconclusive: 'Inconclusive',
  not_reported: 'No result reported', exact: 'Exact term match', close: 'Close term match', broad: 'Broader term',
  different_question: 'Different research question', not_about_the_plant: 'Not about this plant',
}
export function friendly(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not recorded'
  if (Array.isArray(value)) return value.length ? value.map(friendly).join(', ') : 'None recorded'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  const text = String(value)
  return labels[text] || text.replace(/_/g, ' ')
}
export function tierLabel(tier?: string): string { return tier ? friendly(tier) : 'Identification status unavailable' }
export function studyLink(study: Record<string, any>, sourceUrl?: string): string | undefined {
  if (study.pmid && /^\d+$/.test(String(study.pmid))) return `https://pubmed.ncbi.nlm.nih.gov/${study.pmid}/`
  const recordedId = String(study.source_study_id || '')
  if (/^pmid:\d+$/i.test(recordedId)) return `https://pubmed.ncbi.nlm.nih.gov/${recordedId.slice(5)}/`
  if (study.doi) return `https://doi.org/${encodeURIComponent(study.doi)}`
  if (study.nct && /^NCT\d+$/i.test(String(study.nct))) return `https://clinicaltrials.gov/study/${study.nct}`
  if (/^nct:NCT\d+$/i.test(recordedId)) return `https://clinicaltrials.gov/study/${recordedId.slice(4)}`
  return typeof sourceUrl === 'string' && sourceUrl.startsWith('https://') ? sourceUrl : undefined
}
