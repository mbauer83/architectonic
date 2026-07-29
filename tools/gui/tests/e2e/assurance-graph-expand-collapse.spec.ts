/**
 * Walking an assurance neighbourhood has to be reversible.
 *
 * Expansion without collapse makes exploration one-way: every double-click adds nodes,
 * nothing removes them, and the only route back to a readable graph is to reload and start
 * again. The architecture explorer has always toggled; this pins the assurance one to the
 * same contract, and pins that the view is re-framed afterwards so the result is on screen.
 */
import { expect, test } from '@playwright/test'

const HAZARD = 'HAZ@1785068474.d8my.105615'

const openGraph = async (page: import('@playwright/test').Page): Promise<void> => {
  await page.goto(`/assurance/graph?node_id=${encodeURIComponent(HAZARD)}`, { waitUntil: 'load' })
  await expect(page.locator('.graph-svg')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
}

test('double-click expands a neighbour, and again collapses it', async ({ page }) => {
  await openGraph(page)
  const nodes = page.locator('.graph-node')
  const before = await nodes.count()
  const neighbour = nodes.nth(1)

  await neighbour.dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  const expanded = await nodes.count()

  await neighbour.dispatchEvent('dblclick')

  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeLessThan(expanded)
})

test('the collapse affordance is discoverable', async ({ page }) => {
  await openGraph(page)

  // Hint text, plus the badge that marks a node as having neighbours still to fetch. The
  // hint alone was the whole affordance for a while, which meant the only way to learn the
  // graph could be walked was to read a sentence above it.
  await expect(page.locator('.canvas-hint')).toContainText('collapse')
  await expect(page.locator('.expand-badge').first()).toBeAttached()
})

test('the layout toolbar is present and switches the arrangement', async ({ page }) => {
  // The canvas was always shared with the architecture explorer; the controls were not, so
  // this surface had no way to reach the cluster layout its own composable already supported.
  await openGraph(page)
  const arrangement = async (): Promise<string> =>
    page.locator('.graph-node').evaluateAll(
      (nodes) => nodes.map((n) => n.getAttribute('transform') ?? '').join('|'),
    )

  for (const mode of ['Force', 'Cluster', 'Radial']) {
    await expect(page.getByRole('button', { name: mode, exact: true })).toBeVisible()
  }

  const before = await arrangement()
  await page.getByRole('button', { name: 'Cluster', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Cluster', exact: true }))
    .toHaveClass(/spacing-btn--active/)

  await expect.poll(arrangement, { timeout: 20_000 }).not.toBe(before)
})

test('cluster mode bands assurance node types by their place in the analysis', async ({ page }) => {
  await openGraph(page)
  await page.getByRole('button', { name: 'Cluster', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Cluster', exact: true }))
    .toHaveClass(/spacing-btn--active/)

  // The invariant, not a count: whatever this hazard's neighbourhood happens to contain, a
  // banded layout puts different node types on different rows. A single row would mean the
  // placement never reached the layout — the defect this task existed to fix.
  await expect.poll(async () => {
    const ys = await page.locator('.graph-node').evaluateAll((nodes) => nodes.map((n) => {
      const shift = /translate\([-\d.]+,\s*([-\d.]+)\)/.exec(n.getAttribute('transform') ?? '')
      return Math.round(Number(shift?.[1] ?? 0))
    }))
    return new Set(ys).size
  }, { timeout: 20_000 }).toBeGreaterThan(1)
})

test('the graph stays framed after collapsing', async ({ page }) => {
  await openGraph(page)
  const nodes = page.locator('.graph-node')
  const neighbour = nodes.nth(1)
  const before = await nodes.count()

  await neighbour.dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  await neighbour.dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeLessThanOrEqual(before)

  // A fit matches the container's aspect; anything else means content sits outside the view.
  const viewBox = await page.locator('.graph-svg').getAttribute('viewBox')
  const box = await page.locator('.graph-svg').boundingBox()
  const [, , w, h] = (viewBox ?? '').split(' ').map(Number)
  expect(Math.abs((w / h) - (box!.width / box!.height))).toBeLessThan(0.05)
})
