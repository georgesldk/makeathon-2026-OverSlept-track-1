import { test, expect } from '@playwright/test'

test('knowledge map shows real claims and traceable research with layer controls', async ({ page }) => {
  await page.goto('http://127.0.0.1:8443/')
  await page.getByRole('button', { name: 'Knowledge Map' }).click()
  await expect(page.getByRole('heading', { name: 'Historical knowledge map.' })).toBeVisible()
  const map = page.getByRole('region', { name: 'Interactive knowledge map' })
  await expect(map.getByRole('heading', { name: 'Carrots', level: 2 })).toBeVisible({ timeout: 15000 })
  await expect(map.locator('.map-node-candidate').first()).toBeVisible()
  await expect(map.locator('.map-node-claim').first()).toBeVisible()
  await page.getByLabel('Historical claims', { exact: true }).uncheck()
  await expect(map.locator('.map-node-claim')).toHaveCount(0)
  await page.getByLabel('Historical claims', { exact: true }).check()
  await page.getByLabel('Explore research for a claim').selectOption({ index: 1 })
  await expect(map.getByText('Original quotation')).toBeVisible()
  await expect(map.locator('.map-inspector blockquote')).not.toBeEmpty()
  await expect(map.getByText(/study connections returned/)).toBeVisible({ timeout: 15000 })
  await expect(map.getByText('No mapped MeSH concept')).toHaveCount(0)
  const search = await (await page.request.get('http://127.0.0.1:8443/api/entries?q=Carrots&book=culpeper')).json()
  const carrots = search.items.find((entry: {name: string}) => entry.name === 'Carrots')
  const record = await (await page.request.get(`http://127.0.0.1:8443/api/entries/${carrots.id}`)).json()
  let claimWithStudy = ''
  for (const { claim } of record.claims) {
    const details = await (await page.request.get(`http://127.0.0.1:8443/api/claims/${claim.id}`)).json()
    if (details.studies.length) { claimWithStudy = claim.id; break }
  }
  expect(claimWithStudy).not.toBe('')
  await page.getByLabel('Explore research for a claim').selectOption(claimWithStudy)
  await expect(map.locator('.map-node-study').first()).toBeVisible({ timeout: 15000 })
  await expect(map.locator('.map-node-assessment').first()).toBeVisible()
  await map.getByRole('button', { name: 'Open claim in full record' }).click()
  await expect(page.getByRole('heading', { name: 'Studies and assessments' })).toBeVisible()
})
