/**
 * Text a reader needs is shown whole: it wraps, or its control is as wide as it, rather than ending in … or
 * being cut by the edge of its box (owner, 2026-11-26: neither the product nor its figures show cut text).
 *
 * Asserted in the browser because each is layout. An element cuts its text where its content is wider than
 * its box (`scrollWidth > clientWidth`); a `<select>` cuts the option it shows where that option's text is
 * wider than the select's own content box, which only a measurement in the page can tell.
 *
 * The candidates are written through the API and deleted afterwards.
 */
import { expect, test, type Locator, type Page } from '@playwright/test'

const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const INDEX_STORE = 'APP@1786967678.R_K3YAQ'

const written: string[] = []

test.afterEach(async ({ request }) => {
  for (const id of written.splice(0)) {
    const deleted = await request.delete(`/api/candidates/${encodeURIComponent(id)}?dry_run=false`)
    expect(deleted.status(), await deleted.text()).toBe(204)
  }
})

const candidate = async (page: Page, record: Record<string, unknown>): Promise<string> => {
  const created = await page.request.post('/api/candidates', { data: { record, operations: [] } })
  expect(created.ok(), await created.text()).toBe(true)
  const id = ((await created.json()) as { record: { id: string } }).record.id
  written.push(id)
  return id
}

/** Each of *elements* whose content is wider than its box, by its text. */
const cut = (elements: Locator): Promise<string[]> => elements.evaluateAll((all) => all
  .filter((one) => one.scrollWidth > one.clientWidth + 1)
  .map((one) => one.textContent?.trim() ?? ''))

/** Whether the option *select* shows is wider than the room the select gives it. */
const selectCutsItsChoice = (select: Locator): Promise<boolean> => select.evaluate((element) => {
  const one = element as HTMLSelectElement
  const style = getComputedStyle(one)
  const context = document.createElement('canvas').getContext('2d')!
  context.font = style.font
  const text = context.measureText(one.selectedOptions[0]?.text ?? '').width
  // The arrow takes the right end of the box; ~20px of it, and the padding either side.
  const room = one.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - 20
  return text > room
})

/** How many lines *element*'s text takes. */
const lines = (element: Locator): Promise<number> => element.evaluate((one) => {
  const range = document.createRange()
  range.selectNodeContents(one)
  return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size
})

test('the diagram editor shows its hint and its entity names whole', async ({ page }) => {
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('diagram-edit').click()
  await expect(page.getByTestId('layout-lab-canvas').locator('g.lab-element').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.ent-item .ent-name').first()).toBeVisible({ timeout: 30_000 })

  // The hint is longer than the window at this width: it wraps inside the window, every word in view.
  const hint = page.getByTestId('viewport-hint')
  expect.soft(await cut(hint)).toEqual([])
  const hintBox = await hint.boundingBox()
  const windowBox = await hint.evaluate((one: HTMLElement) => {
    const { x, width } = one.offsetParent!.getBoundingClientRect()
    return { x, width }
  })
  expect.soft(hintBox!.x).toBeGreaterThanOrEqual(windowBox.x)
  expect.soft(hintBox!.x + hintBox!.width).toBeLessThanOrEqual(windowBox.x + windowBox.width + 1)
  // Whatever sits in the bottom corners rises above a wrapped hint rather than under it.
  const zoom = await page.locator('.zoom-cluster').boundingBox()
  expect.soft(zoom!.y + zoom!.height).toBeLessThanOrEqual(hintBox!.y + 1)

  expect.soft(await cut(page.locator('.ent-item .ent-name'))).toEqual([])
})

test('a candidate page shows its title on one line and the diagram it is drawn on whole', async ({ page }) => {
  const id = await candidate(page, { name: 'Cached index store', scope: [INDEX_STORE], diagram: DIAGRAM })
  await page.goto(`/candidates/${encodeURIComponent(id)}?diagram=${encodeURIComponent(DIAGRAM)}`, { waitUntil: 'load' })
  const drawOn = page.getByTestId('draw-on')
  await expect(drawOn).toBeVisible({ timeout: 20_000 })
  await page.getByTestId('draw-on').selectOption(DIAGRAM)
  await expect(drawOn).toHaveValue(DIAGRAM)
  expect.soft(await selectCutsItsChoice(drawOn)).toBe(false)
  // The actions wrap beneath the title rather than squeezing it onto two lines.
  expect.soft(await lines(page.locator('.page-hdr h1'))).toBe(1)
})

test('the comparison page shows the diagram its candidates are drawn on whole', async ({ page }) => {
  const one = await candidate(page, { name: 'Queued promotion', scope: [INDEX_STORE], diagram: DIAGRAM })
  const two = await candidate(page, { name: 'Batched promotion', scope: [INDEX_STORE], diagram: DIAGRAM })
  const query = new URLSearchParams([['candidate', one], ['candidate', two], ['diagram', DIAGRAM]])
  await page.goto(`/candidates/compare?${query.toString()}`, { waitUntil: 'load' })
  const drawOn = page.getByTestId('draw-on')
  await expect(drawOn).toHaveValue(DIAGRAM, { timeout: 20_000 })
  expect.soft(await selectCutsItsChoice(drawOn)).toBe(false)
})
