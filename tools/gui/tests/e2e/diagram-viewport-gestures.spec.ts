import { type Page, type Locator } from '@playwright/test'

import { test, expect } from './coverage-fixture'

/**
 * The two gestures a rendered diagram's viewport owes its reader: move the picture, and ask what a
 * box is. They share the primary mouse button, and getting that wrong is invisible to every other
 * suite — the unit tests in `src/ui/composables/__tests__/panGesture.test.ts` assert the decision
 * the composable makes, but only a real render puts a `<g data-entity-id>` under a real pointer.
 *
 * The regression this is here for: panning was declined outright whenever the press landed on a
 * selectable element, so a dense ArchiMate view could only be dragged by its auto-created grouping
 * boxes — the one thing on the picture carrying no entity id.
 */

type DiagramSummary = { artifact_id: string; name: string; diagram_type: string }
type Press = { entity: Locator; x: number; y: number }

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
    localStorage.setItem('arch_group_diagram-collection', 'uncategorized')
  })
})

/**
 * A point on a model entity that a real pointer could actually reach.
 *
 * Containment inside the viewport is the whole criterion. The outermost `[data-entity-id]` on a
 * rendered view is routinely taller than the container it is being panned inside — the first
 * version of this spec pressed the centre of one and landed on `<html>`, well below the diagram,
 * then reported the product broken.
 */
const pressableEntity = async (page: Page): Promise<Press | null> => {
  const viewport = await page.locator('.img-container').boundingBox()
  if (viewport === null) return null
  const entities = page.locator('.svg-wrap [data-entity-id]')
  if (!await entities.first().isVisible().catch(() => false)) return null

  for (const entity of await entities.all()) {
    const box = await entity.boundingBox()
    if (box === null) continue
    const inside = box.x >= viewport.x && box.y >= viewport.y
      && box.x + box.width <= viewport.x + viewport.width
      && box.y + box.height <= viewport.y + viewport.height
    if (inside) return { entity, x: box.x + box.width / 2, y: box.y + box.height / 2 }
  }
  return null
}

/**
 * The first diagram that renders such an entity. Chosen from the live list rather than pinned by
 * id: authoring a diagram is the product working, and a spec that names one reports a false
 * regression the day it is renamed.
 */
const openADiagramWithEntities = async (page: Page): Promise<Press> => {
  const response = await page.request.get('/api/diagrams')
  expect(response.ok()).toBeTruthy()
  const { items } = await response.json() as { items: DiagramSummary[] }
  const candidates = items.filter((d) => d.diagram_type.startsWith('archimate'))
  expect(candidates.length).toBeGreaterThan(0)

  for (const diagram of candidates) {
    await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
    await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 30_000 })
    const press = await pressableEntity(page)
    if (press !== null) return press
  }
  throw new Error('no ArchiMate diagram rendered an entity inside its viewport')
}

const framing = (page: Page) => page.locator('.pan-canvas').getAttribute('style')

test('a drag that starts on a model entity moves the diagram instead of selecting it', async ({ page }) => {
  const { x, y } = await openADiagramWithEntities(page)
  const before = await framing(page)

  await page.mouse.move(x, y)
  await page.mouse.down()
  // In steps, so the pointer crosses the threshold on the way rather than teleporting past it.
  await page.mouse.move(x + 90, y + 60, { steps: 12 })
  await page.mouse.up()

  expect(await framing(page)).not.toBe(before)
  // The click the drag would otherwise have produced must not also select the box it started on:
  // the picture moving and the sidebar changing at once is the confusing half of the ambiguity.
  await expect(page.locator('.svg-wrap .svg-selected')).toHaveCount(0)
})

test('a press on the same spot that does not travel still selects that entity', async ({ page }) => {
  const { x, y } = await openADiagramWithEntities(page)
  const before = await framing(page)

  await page.mouse.click(x, y)

  await expect(page.locator('.svg-wrap .svg-selected').first()).toBeVisible()
  expect(await framing(page)).toBe(before)
})

test('the diagram fills the screen and the page keeps track of whether it still does', async ({ page }) => {
  await openADiagramWithEntities(page)
  const container = page.locator('.img-container')
  const control = page.locator('.viewport-btn', { hasText: 'Fullscreen' })

  await control.click()

  await expect(page.locator('.viewport-btn', { hasText: 'Exit' })).toBeVisible()
  expect(await container.evaluate((el) => document.fullscreenElement === el)).toBe(true)
  await expect(page.locator('.zoom-hint')).toContainText('Esc to exit')

  // Esc is handled by the browser itself, above the page, and a synthetic key press cannot reach
  // it — so the exit is driven through the very call Esc makes. What is under test either way is
  // that the page learns about an exit it did not initiate, which is the half that can break.
  await container.evaluate(() => document.exitFullscreen())

  await expect(control).toBeVisible()
  expect(await page.evaluate(() => document.fullscreenElement)).toBeNull()
})

test('the fullscreen control gives the diagram back too', async ({ page }) => {
  await openADiagramWithEntities(page)
  const control = page.locator('.viewport-btn', { hasText: 'Fullscreen' })

  await control.click()
  await page.locator('.viewport-btn', { hasText: 'Exit' }).click()

  await expect(control).toBeVisible()
  expect(await page.evaluate(() => document.fullscreenElement)).toBeNull()
})

/**
 * A point inside the viewport that no selectable thing occupies — the diagram's own background.
 *
 * Found by asking the document what is actually under each candidate rather than by assuming a
 * corner is empty: a dense view can reach the edges, and a spec that pressed a hardcoded corner
 * would deselect on some diagrams and select on others.
 */
const backgroundPoint = async (page: Page): Promise<{ x: number; y: number }> => {
  const viewport = await page.locator('.img-container').boundingBox()
  expect(viewport).not.toBeNull()
  const box = viewport!
  for (const fx of [0.5, 0.1, 0.9, 0.3, 0.7]) {
    for (const fy of [0.92, 0.06, 0.5, 0.75]) {
      const x = box.x + box.width * fx
      const y = box.y + box.height * fy
      const empty = await page.evaluate(([px, py]) => {
        const el = document.elementFromPoint(px, py)
        if (el === null) return false
        if (el.closest('[data-entity-id], [data-conn-id], [data-subpart]') !== null) return false
        return el.closest('.img-container') !== null && el.closest('button') === null
      }, [x, y])
      if (empty) return { x, y }
    }
  }
  throw new Error('no empty point inside the diagram viewport')
}

test('clicking an entity twice keeps it selected, and clicking away from everything clears it', async ({ page }) => {
  // Clicking the same box used to toggle the selection off. A reader clicks a box twice while
  // reading it, so deselection belongs on the gesture that means "nothing, thanks": a click that
  // lands on no selectable thing.
  const { x, y } = await openADiagramWithEntities(page)
  const selected = page.locator('.svg-wrap .svg-selected')

  await page.mouse.click(x, y)
  await expect(selected.first()).toBeVisible()

  await page.mouse.click(x, y)
  await expect(selected.first()).toBeVisible()

  const empty = await backgroundPoint(page)
  await page.mouse.click(empty.x, empty.y)

  await expect(selected).toHaveCount(0)
})

test('the sidebar follows the diagram into fullscreen, arriving with a selection and leaving with it', async ({ page }) => {
  // Native fullscreen paints nothing outside the element it was requested on, so a sidebar sitting
  // in the layout's third grid column simply vanished on entry and the reader lost the panel
  // explaining whatever they had just clicked. `DiagramSidebarDock` moves it inside instead.
  await openADiagramWithEntities(page)
  const container = page.locator('.img-container')
  const sidebar = page.locator('.sidebar')

  await page.locator('.viewport-btn', { hasText: 'Fullscreen' }).click()
  // The request is asynchronous: wait for the control to report the new state before asking the
  // document about it, or the assertion races the transition it is meant to observe.
  await expect(page.locator('.viewport-btn', { hasText: 'Exit' })).toBeVisible()
  expect(await container.evaluate((el) => document.fullscreenElement === el)).toBe(true)
  // Nothing selected: a panel permanently over a diagram filling the screen covers the drawing for
  // no reason, so it waits to be asked for.
  await expect(sidebar).toHaveCount(0)

  // Entering fullscreen re-fits the diagram to the new space, so a point measured before the
  // transition no longer covers the box it was taken from. Ask again inside the new framing.
  const press = await pressableEntity(page)
  expect(press).not.toBeNull()
  await page.mouse.click(press!.x, press!.y)

  await expect(sidebar).toBeVisible()
  // A direct child of the fullscreen element is the whole point — outside it the browser paints
  // nothing at all, which is how the panel used to disappear on entry.
  expect(await sidebar.evaluate((el) => el.parentElement?.classList.contains('img-container'))).toBe(true)

  // It arrives by flying in, so it is still travelling when it first becomes visible. Wait for the
  // transform to settle before measuring, or the box read is a sample of the animation: the first
  // version of this assertion caught it 23px short of its resting place and reported a layout bug.
  await page.waitForFunction(
    () => getComputedStyle(document.querySelector('.sidebar')!).transform === 'none',
    null,
    { timeout: 5_000 },
  )
  const panel = await sidebar.boundingBox()
  const screen = await container.boundingBox()
  expect(panel!.x + panel!.width).toBeLessThanOrEqual(screen!.x + screen!.width + 1)
  expect(panel!.x).toBeGreaterThan(screen!.x)

  const empty = await backgroundPoint(page)
  await page.mouse.click(empty.x, empty.y)

  await expect(sidebar).toHaveCount(0)
  expect(await container.evaluate((el) => document.fullscreenElement === el)).toBe(true)
})
