import { type Page } from '@playwright/test'

import { test, expect } from './coverage-fixture'

/**
 * Moving about a diagram larger than the window (owner, Q20, Q21, F10): the overview shows while the
 * pointer is over the canvas and never in what the diagram exports; finding an element moves the
 * window to it and selects it.
 *
 * Asserted on a real render, and on invariants of it — never on what the diagram draws today.
 */

const DIAGRAM = '/diagrams/ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => { localStorage.setItem('arch_diagram_reading_flow', '0') })
})

const open = async (page: Page) => {
  await page.goto(DIAGRAM)
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20_000 })
  await expect.poll(() => page.locator('.svg-wrap [data-entity-id]').count(), { timeout: 20_000 }).toBeGreaterThan(1)
}

/** Zoom in at the canvas's top left corner until part of the picture is outside the window. */
const zoomIn = async (page: Page) => {
  const host = (await page.getByTestId('diagram-canvas-host').boundingBox())!
  await page.mouse.move(host.x + 40, host.y + 40)
  for (let step = 0; step < 8; step += 1) await page.mouse.wheel(0, -300)
  return host
}

test('the overview shows while the pointer is over the canvas, and is not in the export', async ({ page }) => {
  await open(page)
  const overview = page.getByTestId('diagram-overview')
  await zoomIn(page)
  await expect(overview).toBeVisible()
  await expect(overview).toHaveCSS('opacity', '1')
  await expect(page.getByTestId('overview-window')).toHaveCount(1)

  await page.mouse.move(2, 2)
  await expect(overview).toHaveCSS('opacity', '0')

  // The picture on the page and the file it downloads as are the picture alone.
  await expect(page.locator('.svg-wrap svg .ov-window, .svg-wrap svg .diagram-overview')).toHaveCount(0)
  await page.getByRole('button', { name: 'Download', exact: true }).click()
  const [file] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'SVG', exact: true }).click(),
  ])
  const stream = await file.createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream) chunks.push(chunk as Buffer)
  const svg = Buffer.concat(chunks).toString('utf8')
  expect(svg).toContain('<svg')
  expect(svg).not.toMatch(/diagram-overview|ov-window|overview-mark/)
})

test('finding an element moves the window to it and selects it', async ({ page }) => {
  await open(page)
  const host = await zoomIn(page)
  const rows = page.locator('.ent-list .ent-item')
  const name = (await rows.last().locator('.ent-name').textContent())!.trim()

  await page.getByTestId('diagram-find').fill(name)
  await expect(rows.first()).toContainText(name)
  await page.getByTestId('diagram-find').press('Enter')

  await expect(page.getByTestId('reader-subject')).toHaveText(name)
  const selected = page.locator('.svg-wrap .svg-selected').first()
  await expect(selected).toBeVisible()
  await expect.poll(async () => {
    const box = await selected.boundingBox()
    if (!box) return false
    const x = box.x + box.width / 2
    const y = box.y + box.height / 2
    return x > host.x && x < host.x + host.width && y > host.y && y < host.y + host.height
  }).toBe(true)
})
