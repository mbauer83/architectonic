import { test, expect } from './coverage-fixture'

/**
 * A bound element shows what it corresponds to in the model, as a link.
 *
 * The binding was stored, verified, reachable through the MCP tools — and shown nowhere. A lane bound
 * to a service looked exactly like an unbound one, and so did a bound action, so the only route from a
 * drawn element to the entity it stands for was to open the file. This asserts the route a reader
 * actually has: select the element, see the correspondence, follow it.
 *
 * Generic on purpose. A binding is `bindings:` on any diagram, so nothing here names a diagram type or
 * an element kind — the spec finds a bound element by the correspondence it declares.
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_diagram-collection', 'platform-core')
  })
})

const DIAGRAM = '/diagrams/ACT@1786234873.w_H9LsR.working-in-a-scratchpad-area'

test('a bound element names what it represents, and the name links to it', async ({ page }) => {
  await page.goto(DIAGRAM)
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20000 })

  // The bound swimlane, found through the mapping rather than by hard-coding its id.
  const lane = page.locator('.svg-wrap a[data-entity-id*="#swimlane/"]')
  await expect.poll(async () => lane.count(), { timeout: 20_000 }).toBeGreaterThan(0)

  // Select each lane until one that declares a correspondence is found; a diagram may hold both.
  const total = await lane.count()
  let shown = false
  for (let index = 0; index < total; index += 1) {
    await lane.nth(index).click()
    if (await page.locator('.det-bindings').count()) { shown = true; break }
  }
  expect(shown, 'no lane in this diagram showed a model correspondence').toBe(true)

  const bindings = page.locator('.det-bindings')
  await expect(bindings).toBeVisible()
  // The kind is shown with the target: "represents" and "traces-to" are different claims.
  await expect(bindings.locator('.chip-kind').first()).not.toBeEmpty()

  const link = bindings.locator('.det-binding-link').first()
  await expect(link).toBeVisible()
  const label = (await link.textContent())?.trim() ?? ''
  expect(label.length, 'the correspondence is labelled').toBeGreaterThan(0)
  expect(label, 'a resolved target shows its name, not its raw id').not.toMatch(/^[A-Z]{3}@/)

  await link.click()
  await expect(page).toHaveURL(/\/entities\//)
})

test('an unbound element shows no correspondence block at all', async ({ page }) => {
  /** Absence has to read as absence: an empty "Model correspondence" heading over nothing would say
   * the element declares something it does not. */
  await page.goto(DIAGRAM)
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20000 })

  const steps = page.locator('.svg-wrap a[data-entity-id]')
  await expect.poll(async () => steps.count(), { timeout: 20_000 }).toBeGreaterThan(0)

  const total = await steps.count()
  let sawUnbound = false
  for (let index = 0; index < total; index += 1) {
    await steps.nth(index).click()
    if (!(await page.locator('.det-bindings').count())) { sawUnbound = true; break }
  }
  expect(sawUnbound, 'every element claimed a correspondence — the negative case is untested').toBe(true)
  await expect(page.locator('.det-bindings')).toHaveCount(0)
})
