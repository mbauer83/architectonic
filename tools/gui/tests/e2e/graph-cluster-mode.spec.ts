/**
 * Switching the free-exploration graph to cluster mode has to stay switched.
 *
 * The cluster layout computes final positions and is therefore complete once it returns.
 * Following it with the force-settle step — the right ending for a force layout, which has to
 * be run to rest — did two things at once: it re-ran the simulation over the banded positions
 * it had just computed, and, because settling declares the force layout current, it reset the
 * recorded mode. The result was a view that looked half-clustered while the toolbar, the edge
 * routing and the next expansion all believed force mode was still in effect.
 *
 * These assert the recorded mode and the arrangement separately, because the failure was
 * precisely that the two disagreed.
 */
import { expect, test, type Page } from '@playwright/test'

const openGraph = async (page: Page): Promise<void> => {
  const res = await page.request.get('/api/entities?limit=1&domain=application')
  const body = (await res.json()) as { items: Array<{ artifact_id: string }> }
  await page.goto(`/graph?id=${encodeURIComponent(body.items[0]!.artifact_id)}`, { waitUntil: 'load' })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
}

const nodeCentres = async (page: Page): Promise<Array<{ x: number; y: number }>> =>
  page.locator('.graph-node').evaluateAll((els) => els.map((el) => {
    const [, x, y] = /translate\(([-\d.]+),\s*([-\d.]+)\)/.exec(el.getAttribute('transform') ?? '') ?? []
    return { x: Number(x), y: Number(y) }
  }))

test('the cluster button stays active after switching', async ({ page }) => {
  await openGraph(page)
  const cluster = page.getByRole('button', { name: 'Cluster', exact: true })

  await cluster.click()

  await expect(cluster).toHaveClass(/spacing-btn--active/)
  await expect(page.getByRole('button', { name: 'Force', exact: true })).not.toHaveClass(/spacing-btn--active/)
})

test('cluster mode arranges nodes in shared rows rather than a force blob', async ({ page }) => {
  /*
   * What separates a banded layout from a force blob is that nodes of one domain share a row —
   * not that there are fewer rows than nodes. This asserted the latter, and broke the moment
   * domains began resolving before the layout ran rather than after: the anchor's own
   * neighbourhood happens to hold one node per domain, so correct banding put each on its own
   * baseline and looked exactly like the blob this was written to catch. Before that fix, some
   * nodes were still 'unknown' at layout time and shared the fallback band by accident — which
   * is what had been passing.
   *
   * One expansion first, so the population is larger than the handful of domains it spans.
   * With one node per domain there is nothing to share and the check is vacuous.
   */
  await openGraph(page)
  const nodes = page.locator('.graph-node')
  // Walked until the population is comfortably larger than the handful of domains it spans,
  // rather than a fixed number of expansions: how much one hop adds is a property of whatever
  // entity the repository happens to return, not something this test should depend on.
  for (let hop = 0; hop < 4 && (await nodes.count()) <= 8; hop++) {
    const before = await nodes.count()
    const expandable = nodes.filter({ has: page.locator('.expand-badge') })
    if (await expandable.count() === 0) break
    await expandable.first().dispatchEvent('dblclick')
    await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
    await page.waitForLoadState('networkidle')
  }

  await page.getByRole('button', { name: 'Cluster', exact: true }).click()
  await page.waitForTimeout(900)

  // A band is a row of a grid and can be more than one node tall, so same-domain nodes share a
  // band rather than an exact baseline. What still separates banding from a blob is that the
  // baselines are *shared*: a force layout leaves almost every node on its own.
  const centres = await nodeCentres(page)
  const rows = new Set(centres.map((c) => Math.round(c.y / 10)))

  expect(centres.length, 'too few nodes for the property to mean anything').toBeGreaterThan(6)
  expect(rows.size, `y-baselines: ${[...rows].sort((a, b) => a - b).join(',')}`)
    .toBeLessThan(centres.length)
})

test('expanding in cluster mode keeps cluster mode', async ({ page }) => {
  await openGraph(page)
  const nodes = page.locator('.graph-node')
  await page.getByRole('button', { name: 'Cluster', exact: true }).click()
  const before = await nodes.count()

  await nodes.filter({ has: page.locator('.expand-badge') }).first().dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)

  await expect(page.getByRole('button', { name: 'Cluster', exact: true })).toHaveClass(/spacing-btn--active/)
})

test('the selected layout button stays readable under the pointer', async ({ page }) => {
  await openGraph(page)
  const cluster = page.getByRole('button', { name: 'Cluster', exact: true })
  await cluster.click()
  await cluster.hover()

  const { color, background } = await cluster.evaluate((el) => {
    const style = getComputedStyle(el)
    return { color: style.color, background: style.backgroundColor }
  })

  expect(color, 'the selected button keeps its light label').toBe('rgb(255, 255, 255)')
  const [r, g, b] = /(\d+), (\d+), (\d+)/.exec(background)!.slice(1).map(Number)
  expect((r + g + b) / 3, `background ${background} is too light for white text`).toBeLessThan(160)
})
