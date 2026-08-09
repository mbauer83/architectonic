import { test, expect } from './coverage-fixture'

/**
 * Slice 1 of the scratchpad, driven as a person drives it.
 *
 * The browser suite is the only layer that exercises the real thing, and this feature is the most
 * interaction-heavy surface in the product — a canvas whose whole value is gestures. It is also why
 * the Phase D evaluation chose HTML notes over a bitmap canvas: every assertion below is a plain
 * Playwright locator, where a canvas library would have needed injected JS handles for all of it.
 *
 * The acceptance question slice 1 answers: **is this usable as a thinking tool with no ontology
 * involvement at all?** So nothing here types a note, and nothing here mentions an element type.
 */

const CANVAS = '[data-testid="scratchpad-canvas"]'

/** Unique per run: without it a second run leaves two rows with one name, and a strict locator
 * cannot choose between them — which reads as a product defect rather than as test residue. */
const RUN = `${Date.now().toString(36)}`

/** Everything this file made, removed at the end. `dry_run=false` because a bare delete plans. */
const created: string[] = []

test.afterAll(async ({ request }) => {
  for (const id of created) {
    await request.delete(`/api/scratchpads/${encodeURIComponent(id)}?dry_run=false`)
  }
})

/** Create a scratchpad through the UI and land on its canvas. */
async function newScratchpad(page: import('@playwright/test').Page, name: string): Promise<string> {
  await page.goto('/scratchpads')
  await page.getByTestId('new-scratchpad-name').fill(`${name} ${RUN}`)
  // Whichever collection this workspace has; the test asserts behaviour, not the group vocabulary.
  const group = page.getByTestId('new-scratchpad-group')
  await group.selectOption({ index: 1 })
  await page.getByRole('button', { name: 'New scratchpad' }).click()
  await expect(page.locator(CANVAS)).toBeVisible({ timeout: 15000 })
  const id = decodeURIComponent(page.url().split('/scratchpads/')[1])
  created.push(id)
  return id
}

/** Double-click the canvas at an offset from its top-left corner, creating a note there. */
async function addNote(page: import('@playwright/test').Page, x: number, y: number, title: string) {
  const canvas = page.locator(CANVAS)
  await canvas.dblclick({ position: { x, y } })
  const editing = page.locator('.sp-note .sp-title:focus')
  await expect(editing).toBeVisible()
  await page.keyboard.press('ControlOrMeta+a')
  await page.keyboard.type(title)
  await page.keyboard.press('Enter')
  await expect(page.locator('.sp-note', { hasText: title })).toBeVisible()
}

test('a scratchpad holds untyped notes and links, and survives a reload', async ({ page }) => {
  await newScratchpad(page, 'E2E thinking')

  await addNote(page, 200, 160, 'Grow into mid-market')
  await addNote(page, 520, 300, 'Self-serve onboarding')

  await expect(page.locator('.sp-note')).toHaveCount(2)
  // Nothing has a type, and the canvas says so rather than demanding one.
  await expect(page.locator('.sp-note .sp-untyped')).toHaveCount(2)

  // Draw a link by dragging the first note's handle onto the second.
  const source = page.locator('.sp-note', { hasText: 'Grow into mid-market' })
  const target = page.locator('.sp-note', { hasText: 'Self-serve onboarding' })
  await source.hover()
  await source.locator('.sp-handle').hover()
  await page.mouse.down()
  await target.hover()
  await page.mouse.up()
  await expect(page.locator('.sp-link:not(.drawing)')).toHaveCount(1)

  // The save is debounced, so the state settles a moment after the last gesture rather than at once.
  await expect(page.getByTestId('save-state')).toHaveText('Saved', { timeout: 15000 })

  await page.reload()
  await expect(page.locator(CANVAS)).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.sp-note')).toHaveCount(2)
  await expect(page.locator('.sp-link:not(.drawing)')).toHaveCount(1)
  // Still the same scratchpad, not a fresh one: the reload restored what was stored for this id.
  await expect(page.getByTestId('scratchpad-name')).toHaveText(`E2E thinking ${RUN}`)
})

test('the canvas writes once when a burst of edits settles, not once per gesture', async ({ page }) => {
  await newScratchpad(page, 'E2E write rate')
  await addNote(page, 200, 160, 'Dragged about')
  await expect(page.getByTestId('save-state')).toHaveText('Saved', { timeout: 15000 })

  const writes: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'PUT' && request.url().includes('/api/scratchpads/')) {
      writes.push(request.url())
    }
  })

  // One continuous drag: dozens of pointer positions, which a per-gesture write would send whole.
  const note = page.locator('.sp-note').first()
  await note.hover()
  await page.mouse.down()
  for (let step = 0; step < 30; step++) {
    await page.mouse.move(300 + step * 6, 260 + step * 3)
  }
  await page.mouse.up()
  await expect(page.getByTestId('save-state')).toHaveText('Saved', { timeout: 15000 })

  // The endpoint sees a save, never a drag.
  expect(writes.length).toBeGreaterThan(0)
  expect(writes.length).toBeLessThanOrEqual(2)
})

test('undo reverses each kind of edit, and redo puts it back', async ({ page }) => {
  await newScratchpad(page, 'E2E undo')
  await addNote(page, 200, 160, 'First thought')
  await addNote(page, 460, 260, 'Second thought')
  await expect(page.locator('.sp-note')).toHaveCount(2)

  // Creating a note and titling it are two edits, and undo reverses them in that order — the title
  // first, then the note. That is what a person means by "undo": the last thing they did.
  await page.getByTestId('undo').click()
  await expect(page.locator('.sp-note', { hasText: 'New note' })).toBeVisible()
  await expect(page.locator('.sp-note')).toHaveCount(2)

  await page.getByTestId('undo').click()
  await expect(page.locator('.sp-note')).toHaveCount(1)

  await page.getByTestId('redo').click()
  await expect(page.locator('.sp-note')).toHaveCount(2)

  // A deletion is undoable too — the history holds documents, so no edit kind is a special case.
  const doomed = page.locator('.sp-note').nth(1)
  await doomed.hover()
  await doomed.locator('.sp-delete').click()
  await expect(page.locator('.sp-note')).toHaveCount(1)
  await page.getByTestId('undo').click()
  await expect(page.locator('.sp-note')).toHaveCount(2)
})

test('a note dropped inside a frame belongs to that area', async ({ page }) => {
  await newScratchpad(page, 'E2E areas')

  // The four frames are seeded, so a new scratchpad opens usable rather than blank.
  await expect(page.locator('.sp-area')).toHaveCount(4)
  await addNote(page, 200, 120, 'Filed by where it sits')

  // Membership is spatial and derived: the server reports it, the canvas does not invent it.
  await expect(page.locator('.sp-note').first()).toHaveAttribute('data-area', /strategy|unfiled/)
})

test('right-clicking the canvas offers a note, or an element the model already has', async ({ page }) => {
  await newScratchpad(page, 'E2E menu')
  const canvas = page.locator(CANVAS)

  // Right-click is "act here". Nothing is added until something in the menu is chosen.
  await canvas.click({ button: 'right', position: { x: 240, y: 180 } })
  await expect(page.getByTestId('canvas-menu')).toBeVisible()
  await expect(page.locator('.sp-note')).toHaveCount(0)

  await page.getByTestId('menu-new-note').click()
  await expect(page.getByTestId('canvas-menu')).toBeHidden()
  await expect(page.locator('.sp-note')).toHaveCount(1)

  // The second entry opens the search in place rather than in a panel elsewhere.
  await canvas.click({ button: 'right', position: { x: 520, y: 320 } })
  await page.getByTestId('menu-add-existing').click()
  const search = page.getByTestId('menu-search').locator('input').first()
  await expect(search).toBeVisible()

  // Whatever this repository holds: the assertion is that a pick binds, not what it binds to.
  await search.fill('a')
  const firstHit = page.locator('[data-testid="canvas-menu"] li[data-result]').first()
  await expect(firstHit).toBeVisible({ timeout: 15000 })
  await firstHit.click()

  await expect(page.getByTestId('canvas-menu')).toBeHidden()
  await expect(page.locator('.sp-note')).toHaveCount(2)
  // A bound note carries the model reference the picker chose, and offers to release it.
  await expect(page.locator('.sp-note.bound')).toHaveCount(1)
  await expect(page.locator('.sp-note .sp-bound')).toBeVisible()
})

test('lift preflights before it writes, and refuses to lift what is undecided', async ({ page }) => {
  await newScratchpad(page, 'E2E lift')
  const canvas = page.locator(CANVAS)

  await addNote(page, 240, 160, 'Grow into mid-market')
  await addNote(page, 520, 160, 'Not decided yet')

  // Nothing is typed, so the whole scratchpad is unliftable — and the dialog says which notes and
  // why rather than failing at the write.
  await canvas.click({ button: 'right', position: { x: 800, y: 420 } })
  await page.getByTestId('menu-lift').click()
  await expect(page.getByTestId('lift-dialog')).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('lift-refused')).toBeVisible()
  await expect(page.getByTestId('lift-confirm')).toBeDisabled()

  // Nothing was written: a preflight is a report.
  await expect(page.locator('.sp-note.bound')).toHaveCount(0)
  await page.getByTestId('lift-close').click()
  await expect(page.getByTestId('lift-dialog')).toBeHidden()
})

test('a scratchpad appears in the list with its note count', async ({ page }) => {
  await newScratchpad(page, 'E2E listed')
  await addNote(page, 200, 160, 'One note')
  await expect(page.getByTestId('save-state')).toHaveText('Saved', { timeout: 15000 })

  await page.goto('/scratchpads')
  const row = page.locator('[data-testid="scratchpad-list"] .row', { hasText: `E2E listed ${RUN}` })
  await expect(row).toBeVisible()
  await expect(row).toContainText('1 note')
})
