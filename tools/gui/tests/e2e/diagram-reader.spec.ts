import { type Page } from '@playwright/test'

import { test, expect } from './coverage-fixture'

/**
 * The diagram reader (B97) on a real render: select, and the rest steps back; reach along the drawn
 * relations; the reading in the address, with Back returning to the previous one.
 *
 * Only a real render maps a PlantUML picture to the model, so only here can it be seen that what is
 * dimmed is what the reading leaves out. The assertions are invariants of that, never counts of what
 * the diagram draws today: authoring an element is the product working.
 */

const DIAGRAM = '/diagrams/ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const SELECTED = '.svg-wrap [data-entity-id*="enterprise-repository"]'

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => { localStorage.setItem('arch_diagram_reading_flow', '0') })
})

const open = async (page: Page, query = '') => {
  await page.goto(`${DIAGRAM}${query}`)
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20_000 })
  await expect.poll(() => page.locator('.svg-wrap [data-entity-id]').count(), { timeout: 20_000 }).toBeGreaterThan(1)
}

/** The ids of every element the picture maps, and of those dimmed. */
const marks = (page: Page) => page.evaluate(() => {
  const ids = (selector: string) =>
    [...new Set([...document.querySelectorAll(selector)].map((element) => element.getAttribute('data-entity-id')))]
  return { all: ids('.svg-wrap [data-entity-id]'), dimmed: ids('.svg-wrap [data-entity-id].reading-dim') }
})

/** The ids the Reading panel lists as drawn and reached. */
const reachedIds = (page: Page) => page.locator('[data-testid="reader-drawn"] [data-reached]')
  .evaluateAll((rows) => [...new Set(rows.map((row) => row.getAttribute('data-reached')))])

test('selecting an element dims what the reading does not reach, and nothing is hidden', async ({ page }) => {
  await open(page)
  const selectedId = await page.locator(SELECTED).first().getAttribute('data-entity-id')
  await page.locator(SELECTED).first().click()

  await expect(page.getByTestId('diagram-reader')).toBeVisible()
  await expect(page.getByTestId('reader-subject')).not.toBeEmpty()
  await expect.poll(async () => (await marks(page)).dimmed.length).toBeGreaterThan(0)

  const { all, dimmed } = await marks(page)
  const reached = await reachedIds(page)
  expect(dimmed).not.toContain(selectedId)
  for (const id of reached) expect(dimmed).not.toContain(id)
  expect(dimmed.length + reached.length + 1).toBe(all.length)

  // Dimmed, never hidden: a dimmed element is still drawn, and clicking it reads it instead.
  const other = page.locator(`.svg-wrap [data-entity-id="${dimmed[0]}"]`).first()
  await expect(other).toBeVisible()
  await other.click({ force: true })
  await expect.poll(async () => (await marks(page)).dimmed).not.toContain(dimmed[0])

  // Clearing gives the picture back whole.
  await page.getByRole('button', { name: 'Clear the reading' }).click()
  await expect(page.getByTestId('diagram-reader')).toHaveCount(0)
  await expect(page.locator('.svg-wrap .reading-dim')).toHaveCount(0)
})

test('reach follows the controls: none each way lights only the selection, all reaches further', async ({ page }) => {
  await open(page)
  await page.locator(SELECTED).first().click()
  await expect(page.getByTestId('diagram-reader')).toBeVisible()
  const oneStep = await reachedIds(page)

  await page.locator('[data-reach="incoming:0"]').click()
  await page.locator('[data-reach="outgoing:0"]').click()
  await expect(page.getByTestId('reader-drawn')).toContainText('Nothing within this reach.')
  const lit = async () => { const { all, dimmed } = await marks(page); return all.length - dimmed.length }
  await expect.poll(lit).toBe(1)

  await page.locator('[data-reach="incoming:all"]').click()
  await page.locator('[data-reach="outgoing:all"]').click()
  await expect(page.locator('[data-reach="outgoing:all"]')).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(async () => (await reachedIds(page)).length).toBeGreaterThanOrEqual(oneStep.length)
  for (const id of oneStep) expect(await reachedIds(page)).toContain(id)
  await expect(page).toHaveURL(/reach=in:all,out:all/)
})

test('the reading is a link, and Back returns to the previous reading', async ({ page, context }) => {
  await open(page)
  await page.locator(SELECTED).first().click()
  await page.locator('[data-reach="incoming:0"]').click()
  await expect(page).toHaveURL(/focus=BOB@[^&]+&reach=in:0,out:1/)
  const first = page.url()

  // A link opened afresh reads the same: the selection and the reach come back from the address.
  const fresh = await context.newPage()
  await fresh.goto(first)
  await expect(fresh.getByTestId('reader-subject')).toHaveText(await page.getByTestId('reader-subject').innerText())
  await expect(fresh.locator('[data-reach="incoming:0"]')).toHaveAttribute('aria-pressed', 'true')
  await fresh.close()

  const dimmed = (await marks(page)).dimmed[0]
  await page.locator(`.svg-wrap [data-entity-id="${dimmed}"]`).first().click({ force: true })
  await expect(page).not.toHaveURL(first)

  await page.goBack()
  await expect(page).toHaveURL(first)
  await expect(page.locator('[data-reach="incoming:0"]')).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(async () => (await marks(page)).dimmed).not.toContain(
    await page.locator(SELECTED).first().getAttribute('data-entity-id'))

  // A change of reach was a reading of its own, and before the first selection there was none.
  await page.goBack()
  await expect(page).toHaveURL(/reach=in:1,out:1/)
  await expect(page.locator('[data-reach="incoming:1"]')).toHaveAttribute('aria-pressed', 'true')
  await page.goBack()
  await expect(page.getByTestId('diagram-reader')).toHaveCount(0)
})

test('the whole reading can be done from the keyboard', async ({ page }) => {
  await open(page)
  await page.getByTestId('diagram-canvas-host').focus()
  await page.keyboard.press('Enter')
  const focused = page.locator('.svg-wrap [data-reading-stop]:focus')
  await expect(focused).toHaveCount(1)
  await expect(focused).toHaveAttribute('aria-label', /, \d+ of \d+$/)

  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('diagram-reader')).toBeVisible()
  await expect(page).toHaveURL(/focus=/)

  await page.keyboard.press('Escape')
  await expect(page.getByTestId('diagram-reader')).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('diagram-canvas-host')).toBeFocused()
})
