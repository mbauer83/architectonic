import { expect, test, type Page } from '@playwright/test'
import { capture, watch, type CaptureProvenance } from './mediaHelpers'

/**
 * The documentation's pictures of a diagram page in its two modes: edit mode on the canvas, and view
 * mode with the Reading panel open.
 *
 * Nothing here writes. Every edit made for a picture is a step of the session's undo history and is
 * left by *Discard and exit*, so the diagram and the model are as they were before the shot.
 */

/** Edited in the figures: an ordinary diagram whose picture is generated from what it draws, so edit mode
 * shows the canvas as most diagrams have it, with no notice about a picture drawn by hand. */
const EDITED = 'ARC@1795678710.xPpzEhH.editing-and-evaluating-architectures-on-the-canvas'
/** The element dragged, and the one its guides line it up with. */
const MOVED = 'APP_qk3Is42'
const ALIGNED_WITH = 'APP_yaxrWl'
/** Read from in view mode. */
const READ = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const READ_FROM = '.svg-wrap [data-entity-id*="enterprise-repository"]'

const provenance = (testName: string, diagram: string): CaptureProvenance => ({
  test_name: testName,
  artifact_ids: [diagram],
  synthetic_augmentation: false,
})

const open = async (page: Page, diagram: string): Promise<void> => {
  await page.goto(`/diagrams/${encodeURIComponent(diagram)}`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => page.locator('.svg-wrap [data-entity-id]').count(), { timeout: 20_000 }).toBeGreaterThan(1)
}

const edit = async (page: Page): Promise<void> => {
  await page.getByTestId('diagram-edit').click()
  await expect(page.getByTestId('layout-lab-canvas').locator('g.lab-element').first()).toBeVisible({ timeout: 30_000 })
  // The figures are of the canvas as an ordinary diagram has it: no notice about a picture drawn by hand.
  await expect(page.getByTestId('edit-body-by-hand')).toHaveCount(0)
}

const leaveWithoutSaving = async (page: Page): Promise<void> => {
  await page.getByRole('button', { name: /Done/ }).click()
  const discard = page.getByTestId('discard-and-exit')
  if (await discard.count()) await discard.click()
}

test.beforeEach(async ({ context }) => {
  // The reading's flow animation would otherwise be photographed mid-run.
  await context.addInitScript(() => { localStorage.setItem('arch_diagram_reading_flow', '0') })
})

test('a diagram in edit mode', async ({ page }) => {
  // The mode itself: the edit bar above the canvas and the sidebar beside it, before anything moves.
  const problems = watch(page)
  await open(page, EDITED)
  await edit(page)
  await expect(page.getByTestId('change-count')).toHaveText('No changes')
  await capture(page, 'diagram-edit-mode.png', provenance('a diagram in edit mode', EDITED))
  await leaveWithoutSaving(page)
  expect(problems, 'runtime problems while capturing diagram-edit-mode.png').toEqual([])
})

test('a diagram mid-drag, with its guides and the change list', async ({ page }) => {
  // The README's claim is the snapping and the one list of what Save writes, so both are on screen: a
  // change already made and listed, and a second drag held where the guides show what it lines up with.
  const problems = watch(page)
  // A taller window than the others: the whole picture fits with paper above it, where the change list
  // opens, so neither the list nor the canvas overview covers any of the picture's words.
  await page.setViewportSize({ width: 1440, height: 1060 })
  await open(page, EDITED)
  await edit(page)
  // The change list opens over what is beside it; with the sidebar closed that is the canvas, so the figure
  // shows no sidebar text cut off under the list. (The sidebar itself is the subject of the edit-mode figure.)
  const panel = page.getByTestId('edit-panel-toggle')
  await panel.click()
  await expect(panel).toHaveAttribute('aria-expanded', 'false')
  const moved = page.locator(`g.lab-element[data-alias="${MOVED}"] .lab-grip`)
  const alignedWith = page.locator(`g.lab-element[data-alias="${ALIGNED_WITH}"] .lab-grip`)
  // The whole picture, fitted to the window the closed sidebar widened, then moved down below where the change
  // list opens (middle button, pressed on the canvas's own paper), so the list covers none of its words.
  const paper = (await page.getByTestId('layout-lab-canvas').boundingBox())!
  const [panX, panY] = [paper.x + paper.width * 0.85, paper.y + paper.height * 0.5]
  const before = (await moved.boundingBox())!
  await page.mouse.move(panX, panY)
  await page.mouse.down({ button: 'middle' })
  await page.mouse.move(panX, panY + 90, { steps: 8 })
  await page.mouse.up({ button: 'middle' })
  await expect.poll(async () => (await moved.boundingBox())!.y).toBeGreaterThan(before.y + 60)
  await moved.click()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByTestId('change-count')).not.toHaveText('No changes')
  // The take-over notice is a toast; it times out on its own, and a figure of it would show a toast.
  await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 })
  await page.getByTestId('change-count').click()
  await expect(page.getByText('Save will write')).toBeVisible()

  const [from, to] = [await moved.boundingBox(), await alignedWith.boundingBox()]
  await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2)
  await page.mouse.down()
  await page.mouse.move(from!.x + from!.width / 2 - 30, to!.y + to!.height / 2 + 1, { steps: 8 })
  await expect(page.getByTestId('alignment-guide')).not.toHaveCount(0)
  await capture(page, 'diagram-edit-guides.png',
    provenance('a diagram mid-drag, with its guides and the change list', EDITED))
  await page.mouse.up()
  await leaveWithoutSaving(page)
  expect(problems, 'runtime problems while capturing diagram-edit-guides.png').toEqual([])
})

test('a diagram read from one element', async ({ page }) => {
  // One step each way is the reading's default; the overview shows only while the window holds part
  // of the picture and the pointer is over the canvas, so the window is zoomed in and the pointer left there.
  const problems = watch(page)
  await open(page, READ)
  await page.locator(READ_FROM).first().click()
  await expect(page.getByTestId('diagram-reader')).toBeVisible()
  await expect(page.locator('[data-reach="incoming:1"]')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('[data-reach="outgoing:1"]')).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => page.locator('.svg-wrap .reading-dim').count()).toBeGreaterThan(0)

  // Zoomed about the selection, so the element read from stays in the middle of what is lit.
  const subject = (await page.locator(READ_FROM).first().boundingBox())!
  await page.mouse.move(subject.x + subject.width / 2, subject.y + subject.height / 2 + 120)
  for (let step = 0; step < 3; step += 1) await page.mouse.wheel(0, -200)
  // Derived is counted after the rest of the panel; a figure of its ellipsis shows a reading half done.
  await expect(page.getByTestId('diagram-reader')).not.toContainText('Derived …', { timeout: 20_000 })
  await expect(page.getByTestId('diagram-overview')).toHaveCSS('opacity', '1')
  await capture(page, 'diagram-reading.png', provenance('a diagram read from one element', READ))
  expect(problems, 'runtime problems while capturing diagram-reading.png').toEqual([])
})
