/**
 * The diagram editor's entity panel stays beside the canvas as the page scrolls.
 *
 * The panel is sticky, and a sticky grid item slides within its grid *container*, not its grid
 * area. It once shared a column with the groupings editor — the only item with an explicit row
 * span, it was auto-placed first, into the left column, and the groupings landed beneath it — so
 * scrolling moved it down over the boxes the author was editing until it covered them.
 *
 * Asserted in the browser because the defect is layout: a CSS grid's auto-placement and a sticky
 * item's constraint rectangle are not things a unit test can observe.
 */
import { expect, test } from '@playwright/test'

const DIAGRAM = 'ARC@1777452513.d8jG_4.what-we-are-trying-to-achieve'

const intersects = (
  a: { top: number, bottom: number, left: number, right: number },
  b: { top: number, bottom: number, left: number, right: number },
): boolean => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom

test('scrolling to the bottom never puts the entity panel over the groupings editor', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 900 })
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}/edit`, { waitUntil: 'load' })
  await expect(page.locator('.entity-list .entity-row').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.grp')).toBeVisible()

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await page.waitForTimeout(300)

  const sidebar = await page.locator('.sidebar').boundingBox()
  const groupings = await page.locator('.grp').boundingBox()
  expect(sidebar).not.toBeNull()
  expect(groupings).not.toBeNull()
  const box = (b: { x: number, y: number, width: number, height: number }) =>
    ({ top: b.y, bottom: b.y + b.height, left: b.x, right: b.x + b.width })

  expect(intersects(box(sidebar!), box(groupings!))).toBe(false)
  // And the panel is where every other diagram surface puts it: beside the canvas, on the right.
  expect(box(sidebar!).left).toBeGreaterThan(box(groupings!).right - 1)
})
