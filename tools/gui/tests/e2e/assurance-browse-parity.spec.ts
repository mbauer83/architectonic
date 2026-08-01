/**
 * The assurance browse surface behaves like the architecture one.
 *
 * It had drifted into a different shape for no reason anyone could name: the wizards were
 * reachable only from a separate hub page, reading a node squeezed the list into 400px beside
 * a detail panel, and the table showed five columns — omitting two fields it nonetheless let
 * you filter by, and the degree the architecture table has always shown.
 *
 * What differs here is only what the assurance model genuinely lacks: its edges are strictly
 * directed with no ontology behind them, so `Connections` breaks into in/out rather than
 * in/sym/out, and the store cannot order by a degree it does not persist.
 */
import { expect, test, type Page } from '@playwright/test'

const openBrowse = async (page: Page): Promise<void> => {
  await page.goto('/assurance', { waitUntil: 'load' })
  await expect(page.locator('table').first()).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState('networkidle')
}

const headers = async (page: Page): Promise<string[]> =>
  page.locator('thead th').evaluateAll((cells) =>
    cells.map((c) => (c.textContent ?? '').trim().split('\n')[0]!.trim()).filter(Boolean))

test('the wizards sit beside the list rather than on a separate page', async ({ page }) => {
  await openBrowse(page)
  const nav = page.locator('.wizard-nav')

  await expect(nav).toBeVisible()
  for (const wizard of ['STPA — hazard analysis', 'CAST — incident analysis', 'Assurance case / GSN']) {
    await expect(nav.getByRole('link', { name: wizard })).toBeVisible()
  }

  // The list keeps the middle of the surface: the nav is to its left, not on top of it.
  const navBox = (await nav.boundingBox())!
  const tableBox = (await page.locator('table').first().boundingBox())!
  expect(navBox.x + navBox.width).toBeLessThanOrEqual(tableBox.x + 1)
})

test('a wizard link marks itself as the current surface', async ({ page }) => {
  await openBrowse(page)

  await expect(page.locator('.wizard-nav .nav-link--active')).toHaveText('All nodes')
})

test('the table shows every field it lets you filter by', async ({ page }) => {
  // Filtering by a value the reader cannot see is what this closes: status and concern_class
  // were both filterable and both invisible.
  await openBrowse(page)

  // Matched by prefix: a header carrying a sub-header ("Connections" over "in / out") or a
  // sort marker renders as one text node, and pinning the exact string would make this a test
  // of the header's decoration rather than of which columns exist.
  const shown = await headers(page)
  for (const column of ['Type', 'Name', 'Status', 'Concern', 'Connections', 'TLP', 'Binding']) {
    expect(shown.some((h) => h.startsWith(column)), `missing column: ${column}`).toBe(true)
  }
})

test('connections show a total broken into in and out, with no symmetric direction', async ({ page }) => {
  await openBrowse(page)

  const sub = await page.locator('thead').innerText()
  expect(sub).toContain('in / out')
  expect(sub, 'assurance edges are strictly directed; a sym column would assert otherwise')
    .not.toContain('sym')

  // At least one node is connected — the invariant, not a count of this particular store.
  const totals = await page.locator('tbody tr td').evaluateAll((cells) =>
    cells.map((c) => (c.textContent ?? '').trim()).filter((t) => /^\d+\s*\(\d+ \/ \d+\)$/.test(t)))
  expect(totals.length, 'no connection cell rendered at all').toBeGreaterThan(0)
  expect(totals.some((t) => !t.startsWith('0')), 'every node reported zero connections').toBe(true)
})

test('opening a node goes to its own page, leaving the list unsqueezed', async ({ page }) => {
  await openBrowse(page)
  const link = page.locator('tbody tr').first().locator('a').first()
  const href = await link.getAttribute('href')
  expect(href).toMatch(/^\/assurance\/node\//)

  await link.click()

  await expect(page).toHaveURL(/\/assurance\/node\//)
  await expect(page.getByRole('link', { name: /Open in browse/ })).toBeVisible({ timeout: 20_000 })
})

test('a legacy ?node_id= deep link lands on the node page', async ({ page }) => {
  // Links to the old side panel are still in the wild — the graph explorer's "back to browse"
  // among them — so the parameter is honoured rather than silently dropped.
  await openBrowse(page)
  const href = (await page.locator('tbody tr').first().locator('a').first().getAttribute('href'))!
  const nodeId = decodeURIComponent(href.replace('/assurance/nodes/', ''))

  await page.goto(`/assurance?node_id=${encodeURIComponent(nodeId)}`, { waitUntil: 'load' })

  await expect(page).toHaveURL(/\/assurance\/node\//, { timeout: 20_000 })
})

test('the list can be read as a treemap, the same two views the architecture catalog offers', async ({ page }) => {
  // Parity, not an approximation of it: the architecture catalog offers Table | Treemap through this
  // same toggle, and an analyst moving between the two areas should not have to learn a second set
  // of controls that look almost the same. A bespoke "Tree" of grouped rows sat in the Treemap
  // button's place for a while, which is how this test came to assert the wrong thing.
  await openBrowse(page)

  await page.getByRole('button', { name: 'Treemap', exact: true }).click()

  await expect(page).toHaveURL(/[?&]view=treemap/)
  await expect(page.locator('.treemap-svg')).toBeVisible({ timeout: 20_000 })

  // Tiles are real nodes, grouped, and clicking one opens that node's page.
  const tiles = page.locator('[data-leaf-id]')
  await expect.poll(async () => tiles.count(), { timeout: 20_000 }).toBeGreaterThan(1)
  await expect(page.locator('.group-label').first()).toBeVisible()

  await tiles.first().click()
  await expect(page).toHaveURL(/\/assurance\/node\//, { timeout: 20_000 })
})

test('the treemap switch is linkable and the table is the default', async ({ page }) => {
  await page.goto('/assurance?view=treemap', { waitUntil: 'load' })
  await expect(page.locator('.treemap-svg')).toBeVisible({ timeout: 20_000 })

  await openBrowse(page)
  await expect(page.locator('table').first()).toBeVisible()
})

test('clicking an analysis in the filing tree scopes the node list', async ({ page }) => {
  // The nav's whole purpose. The scope used to live in a local ref, so every link that named an
  // analysis arrived, set nothing, and appeared to do nothing at all.
  await openBrowse(page)

  const analysisLink = page.locator('.filing-tree .nav-tree__label--link').first()
  await expect(analysisLink).toBeVisible({ timeout: 20_000 })
  const label = (await analysisLink.textContent())?.trim() ?? ''
  await analysisLink.click()

  await expect(page).toHaveURL(/[?&]analysis=/)
  // The picker beside the list agrees with the nav, because both read the same URL.
  await expect(page.locator('.browse-analysis-row')).toContainText(label.slice(0, 12))
})
