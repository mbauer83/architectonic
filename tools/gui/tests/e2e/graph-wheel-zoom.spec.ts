/**
 * Who owns the framing, and when.
 *
 * Animated layouts re-frame the graph on every frame so it stays in view while it grows. Done
 * with a plain fit, that also overwrites whatever the user just did: a wheel zoom during the
 * three seconds an expansion takes was undone on the very next frame, and the control read as
 * simply dead.
 *
 * The rule these tests hold is a handover, not a winner:
 *
 *   - A structural change — expanding, collapsing, changing spacing — *claims* the framing.
 *     It changes what there is to look at, so a zoom from three hops ago must not survive it
 *     and leave the new neighbours off-screen.
 *   - From that moment the user can take it back, and a zoom *during* the settle stands for
 *     the rest of the animation.
 */
import { expect, test, type Page } from '@playwright/test'

const ANCHOR = 'OUT@1780655839.Vhhne7.assurance-analysis-surfaces-modeling-gaps'

const viewBox = async (page: Page): Promise<string> =>
  (await page.locator('.graph-svg').getAttribute('viewBox')) ?? ''

const open = async (page: Page): Promise<void> => {
  await page.goto(`/graph?id=${encodeURIComponent(ANCHOR)}`, { waitUntil: 'load' })
  await expect(page.locator('.graph-svg')).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState('networkidle')
}

/** Zoom at the canvas centre and report the framing immediately after. */
const wheelAtCentre = async (page: Page): Promise<string> => {
  const box = (await page.locator('.graph-svg').boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, -240)
  await page.waitForTimeout(200)
  return viewBox(page)
}

test('a wheel zoom changes the framing and is not undone once the graph settles', async ({ page }) => {
  await open(page)
  await page.waitForTimeout(4000)

  const before = await viewBox(page)
  const zoomed = await wheelAtCentre(page)
  expect(zoomed, 'the wheel did not change the framing at all').not.toBe(before)

  await page.waitForTimeout(2500)
  expect(await viewBox(page), 'the framing was reset after the zoom').toBe(zoomed)
})

test('a wheel zoom mid-animation survives the rest of the animation', async ({ page }) => {
  // The reported case: scroll while the graph is still easing into place. Every frame of that
  // motion used to re-fit, so the zoom lasted exactly one frame.
  await open(page)
  await page.waitForTimeout(300)

  const zoomed = await wheelAtCentre(page)
  await page.waitForTimeout(4000)

  expect(await viewBox(page), 'the animation overwrote the user\'s zoom').toBe(zoomed)
})

test('a wheel zoom after an expansion is not undone by the relayout', async ({ page }) => {
  await open(page)
  await page.waitForTimeout(4000)
  const nodes = page.locator('.graph-node')
  const before = await nodes.count()
  await nodes.filter({ has: page.locator('.expand-badge') }).first().dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)

  const zoomed = await wheelAtCentre(page)
  await page.waitForTimeout(4000)

  expect(await viewBox(page)).toBe(zoomed)
})

test('an expansion re-frames, discarding a zoom set before it', async ({ page }) => {
  // The other half of the handover. Keeping an earlier zoom across an expansion would leave
  // the nodes the user just asked for outside the viewport.
  await open(page)
  await page.waitForTimeout(4000)

  const zoomed = await wheelAtCentre(page)
  await page.waitForTimeout(600)
  expect(await viewBox(page), 'precondition: the zoom should hold while nothing else happens')
    .toBe(zoomed)

  const nodes = page.locator('.graph-node')
  const before = await nodes.count()
  await nodes.filter({ has: page.locator('.expand-badge') }).first().dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  await page.waitForTimeout(4000)

  expect(await viewBox(page), 'the expansion did not reclaim the framing').not.toBe(zoomed)
})
