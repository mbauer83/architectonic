import { test, expect } from './coverage-fixture'

/**
 * Fullscreen on the graph viewport, in a browser — which is the only place it can be tested.
 *
 * jsdom implements none of the Fullscreen API, so the composable's unit tests are about which of
 * request/exit it calls. What they cannot show is the part that made this worth a spec: the graph
 * re-frames against the new space. `fitToView` computes from the canvas's measured width and
 * height, and those are written by a resize observer, so a fit that followed the *toggle* would
 * frame the graph to the size it just left. The fit therefore waits for the resize, and only a
 * real viewport change proves it happens at all.
 *
 * Esc-to-exit is deliberately not asserted here. It is the reason the native API was chosen over a
 * CSS overlay, but the browser handles that key in its own chrome rather than in the page, so
 * Playwright cannot drive it — and what the *code* does on the way back, syncing from
 * `fullscreenchange`, is already covered where it can be: `composables/__tests__/fullscreen.test.ts`.
 */

const ROOT = 'GOL@1780220699.FCfDuc.sustain-unity-of-effort-at-agentic-velocity'
const GRAPH = `/entities/${encodeURIComponent(ROOT)}/graph`

const viewBox = async (page: import('@playwright/test').Page): Promise<string> =>
  (await page.locator('svg.graph-svg').getAttribute('viewBox')) ?? ''

test('the graph viewport goes fullscreen and re-frames against the new space', async ({ page }) => {
  await page.goto(GRAPH)
  await expect(page.locator('svg g.graph-node').first()).toBeVisible()
  const before = await viewBox(page)

  // By accessible name, as the diagram viewport's own spec now does: the control is glyph-only, so
  // its name is the `aria-label` rather than anything a text locator could find.
  const control = page.getByRole('button', { name: 'View fullscreen' })
  await expect(control).toBeVisible()
  await control.click()

  // The frame is what goes fullscreen, so the zoom cluster is still reachable there.
  await expect
    .poll(async () => page.evaluate(() => document.fullscreenElement?.className ?? ''))
    .toContain('canvas-frame')
  await expect(page.getByRole('button', { name: 'Zoom in' })).toBeVisible()
  // And the hint tells the reader how to leave, as it does on a diagram.
  await expect(page.locator('.zoom-hint')).toContainText('Esc to exit')

  // Re-framed: a viewBox computed for the old size would have survived the transition.
  await expect.poll(async () => viewBox(page)).not.toBe(before)

  const exit = page.getByRole('button', { name: 'Exit fullscreen' })
  await expect(exit).toBeVisible()
  await exit.click()

  await expect.poll(async () => page.evaluate(() => document.fullscreenElement === null)).toBe(true)
})

test('clicking blank space deselects, which is what puts the panel away', async ({ page }) => {
  await page.goto(GRAPH)
  await expect(page.locator('svg g.graph-node').first()).toBeVisible()

  // Select something other than the root, so the panel is showing a deliberate choice.
  await page.locator('svg g.graph-node').nth(2).click()
  await expect(page.locator('aside.graph-sidebar')).toContainText('Artifact ID')

  // The top-left corner of the canvas: away from every node, from the controls at top right and
  // from the hint at bottom centre. Clicked by position because the element's own centre is where
  // the root node sits.
  const box = (await page.locator('svg.graph-svg').boundingBox())!
  await page.mouse.click(box.x + 12, box.y + 12)

  await expect(page.locator('aside.graph-sidebar')).not.toContainText('Artifact ID')
})

test('panning across the canvas does not deselect', async ({ page }) => {
  await page.goto(GRAPH)
  await expect(page.locator('svg g.graph-node').first()).toBeVisible()
  await page.locator('svg g.graph-node').nth(2).click()
  await expect(page.locator('aside.graph-sidebar')).toContainText('Artifact ID')

  // Releasing a pan produces a click too; deselecting on it would make the panel impossible to
  // keep open while moving around the graph.
  const box = (await page.locator('svg.graph-svg').boundingBox())!
  await page.mouse.move(box.x + 12, box.y + 12)
  await page.mouse.down()
  await page.mouse.move(box.x + 160, box.y + 120, { steps: 8 })
  await page.mouse.up()

  await expect(page.locator('aside.graph-sidebar')).toContainText('Artifact ID')
})

test('the toolbar is embedded in the page and floats only over a fullscreen canvas', async ({
  page,
}) => {
  await page.goto(GRAPH)
  await expect(page.locator('svg g.graph-node').first()).toBeVisible()

  // Embedded: laid out by the page's header row, and its controls are simply there.
  const toolbar = page.locator('.graph-toolbar')
  await expect(toolbar).not.toHaveClass(/graph-toolbar--floating/)
  await expect(page.getByRole('button', { name: 'Show controls' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Filter', exact: true })).toBeVisible()

  await page.locator('.viewport-btn[aria-label="View fullscreen"]').click()
  await expect
    .poll(async () => page.evaluate(() => document.fullscreenElement !== null))
    .toBe(true)

  // Floating: inside the fullscreen element, because nothing outside it is painted at all.
  await expect(toolbar).toHaveClass(/graph-toolbar--floating/)
  expect(
    await toolbar.evaluate((el) => document.fullscreenElement?.contains(el) ?? false),
  ).toBe(true)

  // Collapsed to a glyph, since the graph is wanted continuously and the controls occasionally.
  const disclosure = page.getByRole('button', { name: 'Show controls' })
  await expect(disclosure).toBeVisible()
  await expect(page.getByRole('button', { name: 'Filter', exact: true })).toBeHidden()

  await disclosure.click()

  await expect(page.getByRole('button', { name: 'Filter', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Hide controls' })).toBeVisible()
})
