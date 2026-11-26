/**
 * Shaping lines on the diagram editor's canvas (sketch 02·3–02·5, Q33, Q35): a moved element's lines
 * keep the course the drag showed when the mouse is released; a line's end goes onto another side from
 * its menu, reached by the keyboard; a double press adds a bend, Straighten drops it, and undo brings it
 * back — each one step.
 *
 * In the browser because the gestures cross three layers — the canvas, the content editor that owns
 * the menus and the page that owns the keys — and the release is a matter of animation frames. Courses
 * are read in the picture's own units, from each line's hit band.
 */
import { expect, test, type Locator, type Page } from '@playwright/test'

const diagram = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'

type XY = [number, number]

const open = async (page: Page): Promise<Locator> => {
  await page.goto(`/diagrams/${encodeURIComponent(diagram)}`)
  await page.getByTestId('diagram-edit').click()
  const canvas = page.getByTestId('layout-lab-canvas')
  await expect(canvas.locator('g.lab-element').first()).toBeVisible({ timeout: 30_000 })
  return canvas
}

/** Take the picture over by hand first, so the courses read are the router's. */
const byHand = async (page: Page, canvas: Locator) => {
  await canvas.locator('g.lab-element .lab-grip').first().click()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('ArrowUp')
  await expect(page.getByText('Arranged by hand', { exact: false }).first()).toBeVisible()
  await page.keyboard.press('Escape')
}

const courseOf = async (canvas: Locator, line: string): Promise<XY[]> => {
  const points = await canvas.locator(`g.lab-line[data-relation="${line}"] .lab-line-hit`).getAttribute('points')
  return (points ?? '').split(' ').filter(Boolean).map((pair) => pair.split(',').map(Number) as XY)
}

/** Where a point of the picture is on screen. */
const onScreen = async (canvas: Locator, [x, y]: XY): Promise<XY> =>
  canvas.evaluate((svg, at) => {
    const point = new DOMPoint(at[0], at[1]).matrixTransform((svg as SVGSVGElement).getScreenCTM() ?? undefined)
    return [point.x, point.y] as XY
  }, [x, y] as XY)

/** The middle of a line's longest segment, on screen: a place to press it. */
const middleOf = async (canvas: Locator, line: string): Promise<XY> => {
  const course = await courseOf(canvas, line)
  const segments = course.slice(1).map((end, index) => [course[index], end] as const)
  const [a, b] = segments.reduce((best, one) =>
    (Math.hypot(one[1][0] - one[0][0], one[1][1] - one[0][1]) > Math.hypot(best[1][0] - best[0][0], best[1][1] - best[0][1])
      ? one : best))
  return onScreen(canvas, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
}

/** The first line on the picture with at least *corners* corners. */
const aLineWith = async (canvas: Locator, corners: number): Promise<string> => {
  for (const one of await canvas.locator('g.lab-line').all()) {
    const line = await one.getAttribute('data-relation')
    if (line !== null && (await courseOf(canvas, line)).length >= corners + 2) return line
  }
  throw new Error(`no line with ${corners} corners`)
}

test('a moved element\'s lines keep the course the drag showed when the mouse is released', async ({ page }) => {
  const canvas = await open(page)
  await byHand(page, canvas)
  const line = await aLineWith(canvas, 0)
  // Drag the element the line ends at, by its middle, a good way down and across.
  const end = (await courseOf(canvas, line)).at(-1) as XY
  const grips = await canvas.locator('g.lab-element .lab-grip').all()
  let grip: Locator | null = null
  for (const one of grips) {
    const [x, y, w, h] = await Promise.all(['x', 'y', 'width', 'height'].map(async (name) => Number(await one.getAttribute(name))))
    if (end[0] >= x - 1 && end[0] <= x + w + 1 && end[1] >= y - 1 && end[1] <= y + h + 1) grip = one
  }
  if (!grip) throw new Error('the line ends at no element')
  const box = await grip.boundingBox()
  if (!box) throw new Error('not drawn')
  const [x, y] = [box.x + box.width / 2, box.y + box.height / 2]
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + 90, y + 70, { steps: 12 })
  await page.waitForTimeout(150)
  const shown = await Promise.all((await canvas.locator('g.lab-line').all()).map(async (one) => one.locator('.lab-line-hit').getAttribute('points')))
  await page.mouse.up()
  await page.waitForTimeout(150)
  const released = await Promise.all((await canvas.locator('g.lab-line').all()).map(async (one) => one.locator('.lab-line-hit').getAttribute('points')))
  expect(released).toEqual(shown)
})

test('a line\'s end goes onto another side from its menu, opened by the keyboard', async ({ page }) => {
  const canvas = await open(page)
  await byHand(page, canvas)
  const line = await aLineWith(canvas, 0)
  const [x, y] = await middleOf(canvas, line)
  await page.mouse.click(x, y)
  await expect(canvas.locator(`[data-selected-line="${line}"]`)).toBeVisible()

  await page.keyboard.press('Shift+F10')
  await page.getByRole('menuitem', { name: 'Move end to side ▸' }).click()
  const now = await page.locator('[role="menuitem"][data-end="to"][aria-current="true"]').getAttribute('data-side')
  const side = now === 'top' ? 'bottom' : 'top'
  await page.locator(`[role="menuitem"][data-end="to"][data-side="${side}"]`).click()

  const course = await courseOf(canvas, line)
  const [last, before] = [course.at(-1) as XY, course.at(-2) as XY]
  // It arrives upright, from above for the top side and from below for the bottom side.
  expect(Math.abs(last[0] - before[0])).toBeLessThan(0.5)
  expect(side === 'top' ? before[1] < last[1] : before[1] > last[1]).toBe(true)
  await expect(page.getByTestId('change-count')).not.toHaveText('No changes')
})

test('a double press adds a bend, Straighten drops it, and undo brings it back', async ({ page }) => {
  const canvas = await open(page)
  await byHand(page, canvas)
  const line = await aLineWith(canvas, 0)
  const [x, y] = await middleOf(canvas, line)
  await page.mouse.click(x, y)
  const handles = canvas.locator(`[data-selected-line="${line}"] .lab-line-handles__bend`)
  const corners = await handles.count()

  await page.mouse.dblclick(x, y)
  await expect(handles).toHaveCount(corners + 1)

  await page.mouse.click(x, y, { button: 'right' })
  await page.getByRole('menuitem', { name: 'Straighten' }).click()
  await expect(handles).toHaveCount(corners)

  await page.getByTestId('edit-undo').click()
  await expect(handles).toHaveCount(corners + 1)
})

test('a picked label drags with a leader to its anchor, and an arrow nudges it two screen pixels', async ({ page }) => {
  // A-02.14/15: the selected line's segment handle sits where its label is drawn and took the press, so the
  // segment moved instead of the label, no leader showed, and the arrows panned the window by a fifth.
  const canvas = await open(page)
  await byHand(page, canvas)
  const label = canvas.locator('g.lab-line-label[data-painted="label"]').first()
  const line = await label.getAttribute('data-relation')
  await label.click({ force: true })
  await expect(canvas.locator(`[data-selected-line="${line}"]`)).toBeVisible()

  const at = await label.boundingBox()
  if (!at) throw new Error('the label is not drawn')
  const [x, y] = [at.x + at.width / 2, at.y + at.height / 2]
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + 30, y + 20, { steps: 6 })
  await expect(canvas.locator('.lab-line-handles__leader')).toHaveCount(1)
  await expect(canvas.locator('.lab-line-handles__anchor')).toHaveCount(1)
  await page.mouse.up()
  await expect(canvas.locator('.lab-line-handles__leader')).toHaveCount(0)

  const before = (await label.boundingBox())?.x ?? 0
  await page.keyboard.press('ArrowRight')
  await expect.poll(async () => ((await label.boundingBox())?.x ?? 0) - before).toBeGreaterThan(1)
  expect(((await label.boundingBox())?.x ?? 0) - before).toBeLessThan(3)
})
