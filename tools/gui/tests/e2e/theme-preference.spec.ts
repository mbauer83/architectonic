import { test, expect } from './coverage-fixture'

/**
 * The interface follows the system's dark setting until the reader chooses a theme in Preferences,
 * and the choice outlives a reload. The diagram stays on light paper whichever theme is worn: the
 * picture was drawn for it, and so were its exports.
 */

type DiagramSummary = { artifact_id: string; diagram_type: string }

const bodyBackground = (): string => getComputedStyle(document.body).backgroundColor

const lightness = (css: string): number => {
  const match = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(css)
  if (match === null) return Number.NaN
  return (Number(match[1]) + Number(match[2]) + Number(match[3])) / 3
}

test.use({ colorScheme: 'dark' })

test('the theme control switches the interface and is remembered across a reload', async ({ page }) => {
  await page.goto('/', { waitUntil: 'load' })
  const html = page.locator('html')
  const body = () => page.evaluate(bodyBackground)

  // Nothing chosen: the system's dark setting applies.
  await expect(html).not.toHaveAttribute('data-theme', /.+/)
  expect(lightness(await body())).toBeLessThan(80)

  await page.getByRole('button', { name: 'Preferences' }).click()
  const panel = page.getByRole('dialog', { name: 'Preferences' })
  await expect(panel.getByRole('radio', { name: 'System' })).toBeChecked()

  await panel.getByRole('radio', { name: 'Light' }).check()
  await expect(html).toHaveAttribute('data-theme', 'light')
  expect(lightness(await body())).toBeGreaterThan(200)

  await page.reload({ waitUntil: 'load' })
  await expect(html).toHaveAttribute('data-theme', 'light')
  expect(lightness(await body())).toBeGreaterThan(200)

  await page.getByRole('button', { name: 'Preferences' }).click()
  await page.getByRole('dialog', { name: 'Preferences' }).getByRole('radio', { name: 'Dark' }).check()
  await expect(html).toHaveAttribute('data-theme', 'dark')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Preferences' })).toHaveCount(0)

  await page.reload({ waitUntil: 'load' })
  await expect(html).toHaveAttribute('data-theme', 'dark')

  await page.getByRole('button', { name: 'Preferences' }).click()
  await page.getByRole('dialog', { name: 'Preferences' }).getByRole('radio', { name: 'System' }).check()
  await expect(html).not.toHaveAttribute('data-theme', /.+/)
  expect(await page.evaluate(() => localStorage.getItem('arch.preferences.theme'))).toBeNull()
})

test('a diagram stays on light paper in the dark theme', async ({ page }) => {
  const response = await page.request.get('/api/diagrams')
  expect(response.ok()).toBe(true)
  const { items } = await response.json() as { items: DiagramSummary[] }
  const diagram = items.find((d) => d.diagram_type.startsWith('archimate')) ?? items[0]
  expect(diagram, 'the repository holds no diagram').toBeDefined()

  await page.goto(`/diagrams/${encodeURIComponent(diagram!.artifact_id)}`, { waitUntil: 'load' })
  const canvas = page.locator('.img-container').first()
  await expect(canvas).toBeVisible({ timeout: 20_000 })

  // The interface around it is dark, the paper is not.
  expect(lightness(await page.evaluate(bodyBackground))).toBeLessThan(80)
  expect(lightness(await canvas.evaluate((el) => getComputedStyle(el).backgroundColor))).toBeGreaterThan(240)
})
