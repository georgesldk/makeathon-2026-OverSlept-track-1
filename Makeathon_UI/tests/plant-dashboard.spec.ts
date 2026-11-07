import { test, expect } from '@playwright/test'

const entryId = 'a'.repeat(64), candidateId = 'b'.repeat(64), claimId = 'c'.repeat(64)
const claim = (id: string, title: string, mapped = false) => ({ claim: { id, source_claim_id: `culpeper:carrots:${id}`, claim_text: title, quote: 'A historical quotation' }, concepts: mapped ? [{ id: 'D008598', name: 'Menstruation', match: 'close' }] : [] })
const entry = {
  entry: { id: entryId, name: 'Carrots', book: 'culpeper' }, book: { source: 'Project Gutenberg' }, image: null,
  preferred_scientific_name: 'Daucus carota L.', description: 'A historical botanical description.',
  names: [{ name: 'Carrots', layer: 'heading', quote: 'Garden Carrots' }],
  candidates: [{ hypothesis: { id: candidateId, accepted_name: 'Daucus carota L.', rank: 'species' }, decision: { tier: 'A', rules: ['A1'], caveats: [] } }],
  claims: [claim('1', 'First unmapped'), claim(claimId, 'Mapped historical claim', true), claim('2', 'Another claim'), claim('3', 'Last claim')],
}
const assessments = Array.from({length: 4}, (_, i) => ({ claim: entry.claims[1].claim, candidate: 'Daucus carota L.', assessment: { id: `assessment-${i}`, evidence_type: 'in_vitro', applicability: 'partial', finding: 'positive' }, study: { title: `Study ${i + 1}`, pmid: '12345678' } }))

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/entries') return route.fulfill({ json: { items: [{ id: entryId, name: 'Carrots', book: 'culpeper', tiers: ['A'], preferred_scientific_name: 'Daucus carota L.', scientific_names: ['Daucus carota L.'] }], has_more: false } })
    if (url.pathname === `/api/entries/${entryId}`) return route.fulfill({ json: entry })
    if (url.pathname === `/api/entries/${entryId}/studies`) return route.fulfill({ json: { items: assessments, has_more: false } })
    if (url.pathname.startsWith('/api/candidates/')) return route.fulfill({ json: { evidence: [], resolutions: [], descriptions: [], has_more: false } })
    if (url.pathname.startsWith('/api/claims/')) return route.fulfill({ json: { units: [], studies: [], related: [], has_more: false } })
    return route.fulfill({ status: 404, json: {} })
  })
})

test('dashboard groups names, selected claims, studies and their sources', async ({ page }) => {
  await page.goto('http://127.0.0.1:8443/')
  await page.getByRole('button', { name: /Culpeper.*Carrots/ }).click()
  await expect(page.getByRole('heading', { name: 'Carrots', exact: true })).toBeVisible()
  await expect(page.getByText('Daucus carota L.').first()).toBeVisible()
  await expect(page.getByText('A historical botanical description.').first()).toBeVisible()
  await page.getByText('Scientific name candidates', { exact: true }).click()
  await expect(page.locator('.plant-dashboard').getByText('Meets identification criteria')).toBeVisible()
  await page.getByText('Historical and common names', { exact: true }).click()
  await expect(page.locator('.dash-name-row').filter({ hasText: 'Garden Carrots' })).toBeVisible()
  const cards = page.locator('.dash-claim')
  await expect(cards.first()).toContainText('Mapped historical claim')
  await expect(cards.first().getByRole('link', { name: /Menstruation/ })).toHaveAttribute('href', 'https://id.nlm.nih.gov/mesh/D008598')
  await page.getByText('Show 1 more historical claims').click()
  await expect(page.locator('.dash-claim').filter({ hasText: 'Last claim' })).toBeVisible()
  await expect(page.locator('#sec-uses .claim-card').filter({ hasText: 'Last claim' })).toBeVisible()
  await expect(page.getByText('Laboratory study (cells or tissue)').first()).toBeVisible()
  await expect(page.locator('.dash-study').first().getByRole('link', { name: /Open original source/ })).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/12345678/')
  await page.getByText('Show 1 more connected assessments').click()
  await expect(page.getByRole('heading', { name: 'Study 4' })).toBeVisible()
  await page.getByRole('button', { name: 'Sources and evidence →' }).click()
  await expect(page.getByRole('heading', { name: 'Candidate identifications' })).toBeVisible()
  await expect(page.getByText('The pipeline found an accepted name in a plant list.')).toBeVisible()
})

test('dashboard handles entries without claims or research', async ({ page }) => {
  await page.route(`**/api/entries/${entryId}`, route => route.fulfill({ json: { ...entry, claims: [] } }))
  await page.route(`**/api/entries/${entryId}/studies`, route => route.fulfill({ json: { items: [], has_more: false } }))
  await page.goto('http://127.0.0.1:8443/')
  await page.getByRole('button', { name: /Culpeper.*Carrots/ }).click()
  await expect(page.getByText('No claims were extracted for this entry.')).toBeVisible()
  await expect(page.getByText('No studies have been assessed for this entry in the current dataset.')).toBeVisible()
})
