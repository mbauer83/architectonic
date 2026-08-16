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

//: The requirement whose realization chain the intent-to-implementation viewpoint is anchored on.
const HERO_ANCHOR = 'REQ@1712870400.peinbQ.tool-interfaces-mcp-cli-rest'

const openGraph = async (page: Page): Promise<void> => {
  const res = await page.request.get('/api/entities?limit=1&domain=application')
  const body = (await res.json()) as { items: Array<{ artifact_id: string }> }
  await page.goto(`/entities/${encodeURIComponent(body.items[0]!.artifact_id)}/graph`, { waitUntil: 'load' })
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

/**
 * A viewpoint execution is arranged by its presentation, and stays that way.
 *
 * `group_by: domain` asks for the layered ordering the ontology declares — intent above,
 * realization descending — and the surface has two layout owners that must not be swapped for one
 * another: the presentation's, and free exploration's. The filter watcher re-arranged through free
 * exploration's, which groups by the `domain` a *graph node* carries. A viewpoint's nodes are still
 * resolving theirs when the population lands, so every node answered `unknown`, every element fell
 * into one box, and elements the presentation had banded across three layers collapsed into one
 * undifferentiated grid.
 *
 * Asserted as "one band per domain, ordered by the ontology" rather than against a population:
 * authoring an element into this chain is the model working, and a test that counts what the
 * chain holds would report that as a regression.
 */
test('a domain-grouped viewpoint keeps the layered ordering its presentation asks for', async ({ page }) => {
  // Hold the per-entity reads back so the population is arranged while its nodes still have no
  // domain of their own. That is the window the defect lived in — with a warm cache the domains
  // land first and the wrong layout owner happens to produce the right picture.
  await page.route(/\/api\/entities\/[^/?]+$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700))
    await route.continue()
  })
  await page.goto(
    `/graph?viewpoint=intent-to-implementation&param.anchor=${encodeURIComponent(HERO_ANCHOR)}`,
    { waitUntil: 'load' },
  )
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
  await expect(page.locator('.domain-chip').first()).toBeVisible()

  // Grouped by the fill the ontology declares per domain, so this reads the bands without naming
  // which elements are in the picture.
  const bandsByDomain = await page.locator('.graph-node').evaluateAll((els) => {
    const ys: Record<string, number[]> = {}
    for (const el of els) {
      const fill = el.querySelector('polygon:not([fill="none"])')?.getAttribute('fill') ?? ''
      const [, y] = /translate\([-\d.]+,\s*([-\d.]+)\)/.exec(el.getAttribute('transform') ?? '') ?? []
      if (fill) (ys[fill] ??= []).push(Number(y))
    }
    return Object.fromEntries(
      Object.entries(ys).map(([fill, values]) => [fill, values.reduce((a, b) => a + b, 0) / values.length]),
    )
  })

  const centres = Object.values(bandsByDomain)
  expect(centres.length, 'the viewpoint draws more than one domain').toBeGreaterThan(1)
  // The failure this exists for: every domain in one box, so every domain shares one band centre.
  expect(new Set(centres.map((y) => Math.round(y))).size, 'each domain has a band of its own')
    .toBe(centres.length)

  // Motivation above application is the ontology's declared order, and the direction the layered
  // reading depends on: intent above, realization descending.
  const motivation = bandsByDomain['#D1BADC']
  const application = bandsByDomain['#B0D0D9']
  if (motivation !== undefined && application !== undefined) {
    expect(motivation, 'motivation is drawn above application').toBeLessThan(application)
  }
})
