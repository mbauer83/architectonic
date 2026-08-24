import { expect, test } from '@playwright/test'

/**
 * A search result says what kind of artifact it is, and what type within that kind.
 *
 * Two defects met in this list. Diagrams could not reach the served window at all — the REST layer
 * bucketed every non-entity record behind every entity, so a query matching forty entities showed
 * none of the diagram the index had ranked top of its kind. And a diagram that did appear showed
 * `diagram` as its type, because that is what its `artifact_type` carries; the specific type was on
 * the wire under `diagram_type` and the view did not read it.
 *
 * Asserted against the real repository, so about invariants rather than counts: which diagram wins a
 * given query is content.
 */

test.describe('search results', () => {
  test('a diagram searched for by its title is in the list', async ({ page }) => {
    await page.goto('/search?q=Why+a+Scratchpad')

    const results = page.locator('.result-id')
    await expect(results.first()).toBeVisible()
    await expect(page.locator('li', { has: page.locator('.result-id') }).filter({
      hasText: 'why-a-scratchpad',
    }).first()).toBeVisible()
  })

  test('a diagram shows its diagram type, not the word diagram, as its type', async ({ page }) => {
    await page.goto('/search?q=Why+a+Scratchpad')
    const row = page.locator('li', { has: page.locator('.result-id') })
      .filter({ hasText: 'why-a-scratchpad' }).first()
    await expect(row).toBeVisible()

    await expect(row.locator('.kind-chip')).toHaveText(/diagram/i)
    await expect(row.locator('.result-type')).not.toHaveText(/^diagram$/i)
  })

  test('the list names each kind rather than lumping them together', async ({ page }) => {
    await page.goto('/search?q=scratchpad')
    await expect(page.locator('.result-id').first()).toBeVisible()

    const kinds = await page.locator('.kind-chip').allTextContents()
    expect(kinds.length).toBeGreaterThan(0)
    expect(new Set(kinds.map((k) => k.trim().toLowerCase())).size).toBeGreaterThan(1)
  })
})
