import { test, expect } from './coverage-fixture'

/**
 * A swimlane header selects its lane, like every other labelled construct in the notation.
 *
 * The renderer was taught to emit `|[[arch://author Author]]|`, PlantUML renders a real anchor for
 * it, and a backend test asserted both. Neither said anything about the viewer, and the viewer
 * resolved nothing: its sentinel index mapped a diagram-local element's `display_alias` only for
 * action, decision and partition, so an unbound lane's own id matched no entity and the anchor was
 * skipped. The header was a link that selected nothing — which is what a reader meets, and what no
 * amount of testing the writer could have found.
 *
 * Asserted through `data-entity-id`, which the viewer stamps on the elements it mapped: an anchor
 * without it is one the viewer does not know about, and clicking it cannot select anything.
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_diagram-collection', 'platform-core')
  })
})

test('a swimlane header is mapped, selects its lane, and shows it in the sidebar', async ({ page }) => {
  await page.goto('/diagrams/ACT@1786234873.w_H9LsR.working-in-a-scratchpad-area')

  const svg = page.locator('.svg-wrap svg')
  await expect(svg).toBeVisible({ timeout: 20000 })

  // Polled rather than sampled: `data-entity-id` is stamped a tick and a frame after the SVG
  // becomes visible, so a single read passes alone and fails under the load of the full suite.
  const laneAnchors = page.locator('.svg-wrap a[data-entity-id*="#swimlane/"]')
  await expect
    .poll(async () => laneAnchors.count(), {
      timeout: 20_000,
      message: 'no lane header carries a mapped entity id — the viewer resolved none of them',
    })
    .toBeGreaterThan(0)

  const laneId = await laneAnchors.first().getAttribute('data-entity-id')
  expect(laneId).toBeTruthy()

  await laneAnchors.first().click()

  // The lane itself is selected — not a neighbour, and not nothing.
  await expect(page.locator(`.svg-wrap [data-entity-id="${laneId}"].svg-selected`).first()).toBeVisible()

  // And its details are shown, which is the half a mapped-but-inert element would still fail.
  const sidebar = page.locator('.sidebar')
  await expect(sidebar).toBeVisible()
  await expect(sidebar).toContainText('Swimlane', { ignoreCase: true })
})

test('selecting a lane header highlights only that lane', async ({ page }) => {
  await page.goto('/diagrams/ACT@1786234873.w_H9LsR.working-in-a-scratchpad-area')
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20000 })

  const laneAnchors = page.locator('.svg-wrap a[data-entity-id*="#swimlane/"]')
  await expect.poll(async () => laneAnchors.count(), { timeout: 20_000 }).toBeGreaterThan(0)

  const laneId = await laneAnchors.first().getAttribute('data-entity-id')
  await laneAnchors.first().click()

  // A lane header is a label in the band and has no shape of its own, so the only elements that may
  // light up are the header's own anchors. The first lane's anchor follows a <polygon> belonging to
  // the content above it, and pairing it as "the lane's shape" would highlight that instead.
  const selected = page.locator('.svg-wrap .svg-selected')
  const mine = page.locator(`.svg-wrap [data-entity-id="${laneId}"]`)
  await expect(selected).toHaveCount(await mine.count())
})


test('no arch:// anchor is left unresolved after mapping', async ({ page }) => {
  /**
   * The assertion that would have caught this, and the one worth keeping: after the viewer has
   * mapped the SVG, no element may still carry an `arch://` href without a `data-entity-id`. An
   * anchor the mapping did not claim is an affordance that lies — a click follows it into a scheme
   * no handler serves.
   *
   * It holds for every step kind at once and needs no knowledge of which kinds exist, so it fails
   * automatically the next time the notation learns one the mapping does not know. That is what the
   * lane-specific specs above cannot do: they had to be written, and nobody wrote one for lanes.
   */
  await page.goto('/diagrams/ACT@1786234873.w_H9LsR.working-in-a-scratchpad-area')
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20000 })

  // Polled: `data-entity-id` is stamped a tick and a frame after the SVG becomes visible, so a
  // single read samples whichever frame it lands on.
  const unresolved = () => page.evaluate(() =>
    Array.from(document.querySelectorAll('.svg-wrap [href^="arch://"], .svg-wrap [*|href^="arch://"]'))
      .filter((el) => !el.getAttribute('data-entity-id'))
      .map((el) => el.getAttribute('href') ?? el.getAttribute('xlink:href') ?? '?'))

  await expect
    .poll(async () => (await unresolved()).length, {
      timeout: 20_000,
      message: 'the viewer left an arch:// anchor unclaimed — clicking it selects nothing',
    })
    .toBe(0)
})
