/**
 * Several shapes selected at once on the diagram editor's canvas (sketch 02·8, Q14): a rectangle
 * selects what it encloses and pressing a selected shape drags them all; the selection's menu aligns
 * and distributes them, each one undoable step.
 *
 * In the browser because the gesture is DOM wiring over three layers — the canvas, the content
 * editor that owns the menu, and the page that owns the keys — which the unit suites test apart.
 * Positions are read in the picture's own units, from each element's grip, so the view growing as
 * shapes move does not change what is measured.
 */
import { expect, test, type Locator, type Page } from '@playwright/test'

const diagram = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'

interface Placed { left: number; top: number; right: number; bottom: number }

const open = async (page: Page): Promise<Locator> => {
  await page.goto(`/diagrams/${encodeURIComponent(diagram)}`)
  await page.getByTestId('diagram-edit').click()
  const canvas = page.getByTestId('layout-lab-canvas')
  await expect(canvas.locator('g.lab-element').first()).toBeVisible({ timeout: 30_000 })
  return canvas
}

/** Team / Project A's elements by the alias the diagram draws each under (Team B's carry a `__2`). */
const TEAM_A: Readonly<Record<string, string>> = {
  'Architect': 'ACT_Nn7Oo7', 'Developer': 'ACT_Pp8Qq8', 'AI Agent': 'ROL_udXPfB', 'Engagement Repository': 'BOB_so7gfN',
}

const teamA = (canvas: Locator, name: string): Locator =>
  canvas.locator(`g.lab-element[data-alias="${TEAM_A[name]}"] .lab-grip`)

const placed = async (grip: Locator): Promise<Placed> => {
  const [x, y, w, h] = await Promise.all(['x', 'y', 'width', 'height'].map(async (name) =>
    Number(await grip.getAttribute(name))))
  return { left: x, top: y, right: x + w, bottom: y + h }
}

const centre = async (grip: Locator): Promise<[number, number]> => {
  const box = await grip.boundingBox()
  if (!box) throw new Error('not drawn')
  return [box.x + box.width / 2, box.y + box.height / 2]
}

/** Shift-click each of *grips*, after a plain click on the first: a selection of exactly them. */
const selectAll = async (page: Page, grips: readonly Locator[]) => {
  await grips[0].click()
  for (const grip of grips.slice(1)) await grip.click({ modifiers: ['Shift'] })
}

const fromMenu = async (page: Page, on: Locator, submenu: string, entry: string) => {
  await on.click({ button: 'right' })
  await page.getByRole('menuitem', { name: submenu }).click()
  await page.getByRole('menuitem', { name: entry, exact: true }).click()
}

test('a rectangle selects what it encloses, and dragging one of them moves them all', async ({ page }) => {
  const canvas = await open(page)
  const names = ['Architect', 'Developer', 'AI Agent']
  const grips = names.map((name) => teamA(canvas, name))
  const boxes = await Promise.all(grips.map(async (grip) => grip.boundingBox()))
  const left = Math.min(...boxes.map((box) => box!.x)) - 4
  const top = Math.min(...boxes.map((box) => box!.y)) - 4
  const right = Math.max(...boxes.map((box) => box!.x + box!.width)) + 4
  const bottom = Math.max(...boxes.map((box) => box!.y + box!.height)) + 4

  // From below and to the right, back up over the three: the paper there is empty.
  await page.mouse.move(right, bottom + 12)
  await page.mouse.down()
  await page.mouse.move((left + right) / 2, bottom, { steps: 4 })
  await page.mouse.move(left, top, { steps: 4 })
  await expect(page.getByTestId('selection-rectangle')).toBeVisible()
  await page.mouse.up()
  await expect(page.getByTestId('selection-announcement')).toHaveText('3 items selected')
  await expect(canvas.locator('[data-selected]')).toHaveCount(3)

  // Taking over the automatic picture may move things, so measure once the picture is by hand.
  await page.keyboard.press('ArrowDown')
  await expect(page.getByText('Arranged by hand', { exact: false }).first()).toBeVisible()
  const before = await Promise.all(grips.map(placed))
  const [x, y] = await centre(grips[1])
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x, y + 30, { steps: 6 })
  await page.mouse.up()
  const after = await Promise.all(grips.map(placed))

  const moved = after.map((one, index) => [one.left - before[index].left, one.top - before[index].top])
  expect(moved[0][1]).toBeGreaterThan(0)
  for (const [dx, dy] of moved) expect([dx, dy]).toEqual(moved[0])
  await expect(page.getByTestId('selection-announcement')).toHaveText('3 items selected')
})

test('aligning left edges is one step, and undo puts them back', async ({ page }) => {
  const canvas = await open(page)
  const grips = [teamA(canvas, 'Architect'), teamA(canvas, 'Engagement Repository')]
  await selectAll(page, grips)
  await expect(page.getByTestId('selection-announcement')).toHaveText('2 items selected')

  await fromMenu(page, grips[0], 'Align ▸', 'Left edges')
  const aligned = await Promise.all(grips.map(placed))
  expect(aligned[0].left).toBe(aligned[1].left)

  await page.getByTestId('edit-undo').click()
  await expect(page.getByTestId('change-count')).toHaveText('No changes')
  const undone = await Promise.all(grips.map(placed))
  expect(undone[0].left).not.toBe(undone[1].left)
})

test('distributing horizontally leaves equal gaps and keeps the outer two', async ({ page }) => {
  const canvas = await open(page)
  const grips = ['Architect', 'Developer', 'AI Agent'].map((name) => teamA(canvas, name))
  // The middle one nudged off centre first, by hand, so the gaps start unequal.
  await grips[1].click()
  for (let step = 0; step < 3; step += 1) await page.keyboard.press('ArrowRight')
  await selectAll(page, grips)
  const before = (await Promise.all(grips.map(placed))).sort((one, other) => one.left - other.left)
  expect(Math.abs((before[1].left - before[0].right) - (before[2].left - before[1].right))).toBeGreaterThan(8)

  await fromMenu(page, grips[1], 'Distribute ▸', 'Horizontally')
  const after = (await Promise.all(grips.map(placed))).sort((one, other) => one.left - other.left)
  // Kept, to the whole pixel the server rounds a corner to.
  expect(Math.abs(after[0].left - before[0].left)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(after[2].left - before[2].left)).toBeLessThanOrEqual(0.5)
  const gaps = [after[1].left - after[0].right, after[2].left - after[1].right]
  expect(Math.abs(gaps[0] - gaps[1])).toBeLessThanOrEqual(1)
})
