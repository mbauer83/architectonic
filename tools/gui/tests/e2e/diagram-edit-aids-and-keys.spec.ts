/**
 * @verifies REQ@1795678685.0iGUiHR  edit a diagram on its canvas
 *
 * The diagram page's window and edit canvas by pointer aids and by keyboard (sketch 01·1–01·3, 02·1, 02·9;
 * Q7, Q8): the zoom cluster and its keys, no double-click reset, E to edit, alignment guides while a shape
 * is dragged and gone after the drop, Tab through the shapes with a focus ring, the leave choice walked
 * by the arrows, and the reader's legend and title kept on the edit canvas (owner, 2026-11-25).
 *
 * Nothing here saves: every edit is left by Discard and exit.
 */
import { expect, test, type Page } from '@playwright/test'

const diagram = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'

const open = async (page: Page) => {
  await page.goto(`/diagrams/${encodeURIComponent(diagram)}`)
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 30_000 })
}

const editing = async (page: Page) => {
  await expect(page.getByTestId('layout-lab-canvas').locator('g.lab-element').first()).toBeVisible({ timeout: 30_000 })
}

test('the zoom cluster and the keys 0, + and − zoom the window; a double-click does not reset it', async ({ page }) => {
  await open(page)
  const percent = page.getByTestId('zoom-percent')
  const fitted = await percent.innerText()
  await page.getByTestId('zoom-in').click()
  await expect(percent).not.toHaveText(fitted)
  const zoomed = await percent.innerText()

  const host = page.getByTestId('diagram-canvas-host')
  const box = await host.boundingBox()
  await page.mouse.dblclick(box!.x + 20, box!.y + box!.height - 60)
  await expect(percent).toHaveText(zoomed)

  await host.focus()
  await page.keyboard.press('0')
  await expect(percent).toHaveText(fitted)
  await page.keyboard.press('-')
  await expect(percent).not.toHaveText(fitted)
})

test('E edits; a dragged element shows its guides, which go after the drop', async ({ page }) => {
  await open(page)
  await page.getByTestId('diagram-canvas-host').focus()
  await page.keyboard.press('e')
  await editing(page)

  const architect = page.locator('g.lab-element[data-alias="ACT_Nn7Oo7"] .lab-grip')
  const repository = page.locator('g.lab-element[data-alias="BOB_so7gfN"] .lab-grip')
  const [from, to] = [await architect.boundingBox(), await repository.boundingBox()]
  await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2)
  await page.mouse.down()
  // Up beside the repository, its middle level with the repository's.
  await page.mouse.move(from!.x + from!.width / 2 - 30, to!.y + to!.height / 2 + 1, { steps: 8 })
  // A guide is a line one pixel wide, which Playwright counts as not visible: it is asked to be there.
  await expect(page.getByTestId('alignment-guide')).not.toHaveCount(0)
  await page.mouse.up()
  await expect(page.getByTestId('alignment-guide')).toHaveCount(0)

  await page.getByRole('button', { name: /Done/ }).click()
  await page.getByTestId('discard-and-exit').click()
})

test('Enter goes in, Tab walks the shapes with a ring, and the leave choice follows the arrows', async ({ page }) => {
  await open(page)
  await page.getByTestId('diagram-edit').click()
  await editing(page)
  await page.locator('.content-canvas').focus()
  await page.keyboard.press('Enter')
  const announced = page.getByTestId('selection-announcement')
  await expect(announced).toContainText('1 of')
  await page.keyboard.press('Tab')
  await expect(announced).toContainText('2 of')
  await page.keyboard.press('Shift+Enter')
  await page.keyboard.press('ArrowRight')
  await expect(page.getByTestId('focus-ring')).toBeVisible()

  await page.keyboard.press('Enter')
  await page.keyboard.press('ArrowDown')
  await page.getByRole('button', { name: /Done/ }).click()
  await expect(page.getByTestId('save-and-exit')).toBeFocused()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByTestId('discard-and-exit')).toBeFocused()
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await expect(page.getByTestId('keep-editing')).toBeFocused()
  await page.getByTestId('discard-and-exit').click()
})

test('the legend and the title the reader sees stay on the edit canvas', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: /Display options/ }).click()
  await page.getByLabel('Explain the notation, in the image').check()
  await page.getByTestId('diagram-edit').click()
  await editing(page)
  const around = page.getByTestId('canvas-surround')
  await expect(around).toHaveCount(2)
  await expect(around.locator('text').filter({ hasText: 'element kinds' }).first()).toBeAttached()
})
