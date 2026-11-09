import { test, expect } from './coverage-fixture'

/**
 * A free exploration draws the explored entity's relations, and those between its neighbours only
 * when the reader asks for them.
 *
 * The graph still loads every model relation among the nodes it holds; what the checkbox changes is
 * the picture. Asserted against the rule rather than a count, because the neighbourhood is live model
 * content: with the box clear, every drawn relation has the root at one end.
 */

const ROOT = 'GOL@1780220699.FCfDuc.sustain-unity-of-effort-at-agentic-velocity'
const GRAPH = `/entities/${encodeURIComponent(ROOT)}/graph`

const drawnEnds = (page: import('@playwright/test').Page) =>
  page.locator('svg g.graph-edge').evaluateAll((edges) =>
    edges.map((edge) => [edge.getAttribute('data-source'), edge.getAttribute('data-target')]))

test('relations between neighbours are off by default and drawn on request', async ({ page }) => {
  await page.goto(GRAPH)
  await expect.poll(async () => page.locator('svg g.graph-edge').count()).toBeGreaterThan(0)

  const toggle = page.getByTestId('neighbour-relations-toggle')
  await expect(toggle).not.toBeChecked()

  // `evaluateAll` samples one frame, so the rule is polled rather than read once.
  await expect.poll(async () =>
    (await drawnEnds(page)).every(([source, target]) => source === ROOT || target === ROOT)).toBe(true)
  const starCount = await page.locator('svg g.graph-edge').count()

  await toggle.check()

  // This root's neighbourhood is the dense one `graph-filter.spec.ts` was written against: its
  // neighbours are related among themselves, which is what makes the default worth having.
  await expect.poll(async () =>
    (await drawnEnds(page)).filter(([source, target]) => source !== ROOT && target !== ROOT).length,
  ).toBeGreaterThan(0)

  await toggle.uncheck()
  await expect.poll(async () => page.locator('svg g.graph-edge').count()).toBe(starCount)
})
