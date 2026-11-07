import { test, expect } from '@playwright/test'

const entries = [
  { id: '1', book: 'culpeper', name: 'Carrots', preferred_scientific_name: 'Daucus carota L.', tiers: ['A'], image: null },
  { id: '2', book: 'culpeper', name: 'Unknown family', preferred_scientific_name: 'Unmapped plant', tiers: ['B'], image: null },
  { id: '3', book: 'culpeper', name: 'Broken photograph', preferred_scientific_name: 'Daucus carota L.', tiers: ['A'], image: { image_url: 'https://example.invalid/plant.jpg', creator: 'Photographer', license_url: 'https://creativecommons.org/licenses/by/4.0/', occurrence_url: 'https://www.gbif.org/occurrence/1' } },
]
test('Atlas uses family artwork and a fallback when a photograph fails', async ({ page }) => {
  await page.route('**/api/entries?*', route => route.fulfill({ json: { items: entries, has_more: false, total: entries.length } }))
  await page.route('https://example.invalid/**', route => route.abort())
  await page.goto('http://127.0.0.1:8443/')
  await page.getByRole('button', { name: 'Atlas', exact: true }).click()
  await page.locator('.atlas-book-card').filter({ hasText: 'Culpeper' }).click()
  await page.locator('.atlas-families button').filter({ hasText: 'Apiaceae' }).click()
  await expect(page.locator('.atlas-bubble svg[data-family-icon="Apiaceae"]').first()).toBeAttached()
  await page.locator('.atlas-list button').filter({ hasText: 'Carrots' }).click()
  await expect(page.locator('.atlas-plant-photo svg')).toHaveAttribute('data-family-icon', 'Apiaceae')
  await page.locator('.atlas-list button').filter({ hasText: 'Broken photograph' }).click()
  await expect(page.locator('.atlas-plant-photo svg')).toHaveAttribute('data-family-icon', 'Apiaceae')
  await expect(page.locator('.atlas-image-credit')).toHaveCount(0)
  await page.getByRole('button', { name: '‹ All families' }).click()
  await page.locator('.atlas-families button').filter({ hasText: 'Family not recorded' }).click()
  await page.locator('.atlas-list button').filter({ hasText: 'Unknown family' }).click()
  await expect(page.locator('.atlas-plant-photo svg')).toHaveAttribute('data-family-icon', 'fallback')
})
