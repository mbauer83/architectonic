/**
 * Two orientation affordances on the free-exploration graph.
 *
 * 1. **The anchor is marked, permanently.** A viewpoint execution rings its anchors, but free
 *    exploration marked nothing — so a few expansions in, the entity the walk started from was
 *    indistinguishable from the dozens reached since, and there was no way to find your way
 *    back to it. The ring is the same one anchored presentations use.
 * 2. **The sidebar headline is the way through to the entity.** It read "Details", a caption
 *    that names nothing and goes nowhere, while the diagram sidebar had shown the entity's own
 *    name as a link to its page all along.
 */
import { expect, test, type Page } from '@playwright/test'

const ANCHOR = 'OUT@1780655839.Vhhne7.assurance-analysis-surfaces-modeling-gaps'

/** Nodes drawn with the anchor halo: an unfilled ring outside the node's own shape. */
const haloed = (page: Page) =>
  page.locator('.graph-node polygon[fill="none"][stroke="#1e293b"]')

const openGraph = async (page: Page): Promise<void> => {
  await page.goto(`/entities/${encodeURIComponent(ANCHOR)}/graph`, { waitUntil: 'load' })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
  await expect(page.locator('.graph-svg')).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState('networkidle')
}

test('the entity the walk started from carries the anchor ring', async ({ page }) => {
  await openGraph(page)

  // One anchor, because free exploration opens on exactly one entity. An invariant of the
  // mode, not a count of whatever this particular neighbourhood happens to contain.
  await expect(haloed(page)).toHaveCount(1)
})

test('the anchor ring survives expansion', async ({ page }) => {
  await openGraph(page)
  const nodes = page.locator('.graph-node')
  const before = await nodes.count()

  await nodes.filter({ has: page.locator('.expand-badge') }).first().dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  await page.waitForLoadState('networkidle')

  // Permanent: the marking is what the reader navigates back by, so it has to outlast the
  // expansions that make navigating back necessary in the first place.
  await expect(haloed(page)).toHaveCount(1)
})

test('the sidebar headline names the selected entity and links to its page', async ({ page }) => {
  await openGraph(page)

  // Opening the graph selects the entity it opened on, so the headline names it straight
  // away rather than showing a caption until something is clicked.
  const headline = page.locator('.sidebar-title a')
  await expect(headline).toBeVisible({ timeout: 20_000 })

  const name = (await headline.textContent())?.trim() ?? ''
  expect(name).not.toBe('')
  expect(name).not.toBe('Details')
  expect(await headline.getAttribute('href')).toBe(`/entities/${ANCHOR}`)

  // Selecting a different node re-points the headline at that entity, not the one before it.
  // Pick a node whose label differs from the current headline — clicking a same-named
  // node would satisfy the intent yet fail the "changed" assertion under load.
  await page.locator('.graph-node').filter({ hasNotText: name }).first().click()
  await expect.poll(async () => headline.textContent(), { timeout: 20_000 }).not.toBe(name)

  await headline.click()
  await expect(page).toHaveURL(/\/entity\?id=/)
})
