/**
 * Opening a graph must settle on one frame, not zoom through several.
 *
 * Three separate causes used to make the view jump on load, and each produced a frame that
 * was correct for a state nobody asked to see: the root node was published before its
 * neighbourhood and got framed on its own; a fit computed over the empty population counted
 * as a fit, so the first real nodes painted into a frame measured without them; and the
 * canvas column was sized by its header's intrinsic width, so it widened as the header's
 * controls filled in and dragged the fit along with it.
 *
 * The invariant that rules all three out: the graph is painted only once a fit has landed for
 * the population and container being painted. This asserts the observable consequence — no
 * superseded framing stays on screen long enough to be seen — rather than any of the three
 * mechanisms, so it keeps holding if the next cause is a fourth one.
 */
import { expect, test, type Page } from '@playwright/test'

interface Frame { viewBox: string; visible: boolean; nodes: number }
/** A framing plus how many animation frames it stayed on screen. */
interface Held extends Frame { frames: number }

const recordLoad = async (page: Page, url: string): Promise<Held[]> => {
  const frames: Held[] = []
  await page.exposeFunction('__frame', (f: Frame) => {
    const last = frames[frames.length - 1]
    if (last && last.viewBox === f.viewBox && last.visible === f.visible) last.frames += 1
    else frames.push({ ...f, frames: 1 })
  })
  await page.addInitScript(() => {
    const tick = (): void => {
      const svg = document.querySelector('.graph-svg')
      if (svg !== null) {
        void (window as unknown as { __frame: (f: unknown) => void }).__frame({
          viewBox: svg.getAttribute('viewBox') ?? '',
          visible: getComputedStyle(svg).visibility === 'visible',
          nodes: document.querySelectorAll('.graph-node').length,
        })
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
  await page.goto(url, { waitUntil: 'load' })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
  await page.waitForTimeout(2500)
  return frames
}

const anchorId = async (page: Page): Promise<string> => {
  const res = await page.request.get('/api/entities?limit=1&domain=application')
  const body = (await res.json()) as { items: Array<{ artifact_id: string }> }
  return body.items[0]!.artifact_id
}

test('the graph is framed once, and never while it is still loading', async ({ page }) => {
  const id = await anchorId(page)

  const frames = await recordLoad(page, `/entities/${encodeURIComponent(id)}/graph`)

  const painted = frames.filter((f) => f.visible && f.nodes > 0)
  expect(painted.length, 'the graph never became visible').toBeGreaterThan(0)

  // Measured by persistence, not by counting distinct values.
  //
  // The surrounding chrome settles after the graph does — the domain legend renders once the
  // domains resolve, which changes the canvas height, and the ResizeObserver that triggers
  // the refit necessarily runs *after* that layout pass. One frame is therefore painted at
  // the previous fit. Hiding the canvas for it would trade an imperceptible 16ms difference
  // for a blink on every window resize, so it is left alone and bounded here instead.
  //
  // This still fails hard on the defect it was written for: those framings were a 4x zoom
  // apart and each held the screen for hundreds of milliseconds.
  const lingering = painted.slice(0, -1).filter((f) => f.frames > 2)
  expect(
    lingering.map((f) => `${f.viewBox} (${f.frames} frames)`),
    'a superseded framing stayed on screen long enough to be seen',
  ).toEqual([])

  // The framing the user is left with has to be a real fit, not the container rectangle.
  expect(painted[painted.length - 1]!.viewBox).not.toMatch(/^0 0 /)
})

test('the sidebar stays inside the viewport while the header fills in', async ({ page }) => {
  const id = await anchorId(page)
  await page.goto(`/entities/${encodeURIComponent(id)}/graph`, { waitUntil: 'load' })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
  await page.waitForTimeout(1500)

  const sidebar = await page.locator('.graph-sidebar').boundingBox()
  const viewport = page.viewportSize()!

  expect(sidebar!.x + sidebar!.width).toBeLessThanOrEqual(viewport.width)
})
