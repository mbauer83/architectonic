import { expect, test, type Page } from '@playwright/test'
import { capture, watch, type CaptureProvenance } from './mediaHelpers'

/**
 * The documentation's pictures of a diagram page in its two modes: edit mode on the canvas, and view
 * mode with the Reading panel open.
 *
 * Nothing here writes. Every edit made for a picture is a step of the session's undo history and is
 * left by *Discard and exit*, so the diagram and the model are as they were before the shot.
 */

const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const ARCHITECT = 'ACT_Nn7Oo7'
const REPOSITORY = 'BOB_so7gfN'
const READ_FROM = '.svg-wrap [data-entity-id*="enterprise-repository"]'

const provenance = (testName: string): CaptureProvenance => ({
  test_name: testName,
  artifact_ids: [DIAGRAM],
  synthetic_augmentation: false,
})

const open = async (page: Page): Promise<void> => {
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => page.locator('.svg-wrap [data-entity-id]').count(), { timeout: 20_000 }).toBeGreaterThan(1)
}

const edit = async (page: Page): Promise<void> => {
  await page.getByTestId('diagram-edit').click()
  await expect(page.getByTestId('layout-lab-canvas').locator('g.lab-element').first()).toBeVisible({ timeout: 30_000 })
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
  await open(page)
  await edit(page)
  await expect(page.getByTestId('change-count')).toHaveText('No changes')
  await capture(page, 'diagram-edit-mode.png', provenance('a diagram in edit mode'))
  await leaveWithoutSaving(page)
  expect(problems, 'runtime problems while capturing diagram-edit-mode.png').toEqual([])
})

test('a diagram mid-drag, with its guides and the change list', async ({ page }) => {
  // The README's claim is the snapping and the one list of what Save writes, so both are on screen: a
  // change already made and listed, and a second drag held where the guides show what it lines up with.
  const problems = watch(page)
  await open(page)
  await edit(page)
  const architect = page.locator(`g.lab-element[data-alias="${ARCHITECT}"] .lab-grip`)
  const repository = page.locator(`g.lab-element[data-alias="${REPOSITORY}"] .lab-grip`)
  // Zoomed in on the part being arranged, so the guides read at the width the README renders at.
  const near = (await repository.boundingBox())!
  await page.mouse.move(near.x, near.y)
  for (let step = 0; step < 4; step += 1) await page.mouse.wheel(0, -200)
  await architect.click()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByTestId('change-count')).not.toHaveText('No changes')
  // The take-over notice is a toast; it times out on its own, and a figure of it would show a toast.
  await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 })
  await page.getByTestId('change-count').click()
  await expect(page.getByText('Save will write')).toBeVisible()

  const [from, to] = [await architect.boundingBox(), await repository.boundingBox()]
  await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2)
  await page.mouse.down()
  await page.mouse.move(from!.x + from!.width / 2 - 30, to!.y + to!.height / 2 + 1, { steps: 8 })
  await expect(page.getByTestId('alignment-guide')).not.toHaveCount(0)
  await capture(page, 'diagram-edit-guides.png', provenance('a diagram mid-drag, with its guides and the change list'))
  await page.mouse.up()
  await leaveWithoutSaving(page)
  expect(problems, 'runtime problems while capturing diagram-edit-guides.png').toEqual([])
})

test('a diagram read from one element', async ({ page }) => {
  // One step each way is the reading's default; the overview shows only while the window holds part
  // of the picture and the pointer is over the canvas, so the window is zoomed in and the pointer left there.
  const problems = watch(page)
  await open(page)
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
  await capture(page, 'diagram-reading.png', provenance('a diagram read from one element'))
  expect(problems, 'runtime problems while capturing diagram-reading.png').toEqual([])
})
