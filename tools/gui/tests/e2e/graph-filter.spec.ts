import { test, expect } from './coverage-fixture'

/**
 * The legibility control over the complete edge set, against the real application.
 *
 * Free exploration draws every model relation among the nodes it shows — correct, and 1.4x to 3.5x
 * more edges than the star it replaced. The filter is what keeps that readable. Three things have
 * to hold in a browser and cannot be shown by a unit test:
 *
 * - the facet values come from the *loaded* graph and from the meta-ontology's own declaration,
 *   fetched over the wire, so a wrong URL or a schema that does not decode leaves no control at all
 *   rather than an empty one (which is exactly how the first build of this failed: the read went to
 *   `/ontology/classification-levels` without the `/api` prefix, the SPA fallback answered 200 with
 *   HTML, and the panel silently never mounted);
 * - excluding actually removes nodes from the picture;
 * - the selection is in the URL, so a filtered graph is a link somebody else can open.
 */

const ROOT = 'GOL@1780220699.FCfDuc.sustain-unity-of-effort-at-agentic-velocity'
const GRAPH = `/entities/${encodeURIComponent(ROOT)}/graph`

test('the filter offers what the loaded graph contains, under the declared level labels', async ({
  page,
}) => {
  await page.goto(GRAPH)

  // Named "Filter": the chevron is aria-hidden, being decoration rather than the name.
  const summary = page.getByRole('button', { name: 'Filter', exact: true })
  await expect(summary).toBeVisible()

  await summary.click()

  // The labels are the meta-ontology's own, arriving over the wire rather than written here.
  // Asserted through each level's own group rather than by text: the sidebar shows a "Domain"
  // field for the selected entity too, and matching on text alone finds both.
  await expect(page.getByRole('group', { name: 'Domain' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Entity type' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Relationship type' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Entity type' }).getByRole('button')).not.toHaveCount(
    0,
  )
})

test('excluding a type removes it from the picture and says so', async ({ page }) => {
  await page.goto(GRAPH)
  await page.getByRole('button', { name: 'Filter', exact: true }).click()

  const typeGroup = page.getByRole('group', { name: 'Entity type' })
  const first = typeGroup.getByRole('button').first()
  const value = ((await first.textContent()) ?? '').trim()
  const before = await page.locator('svg g.graph-node').count()

  await first.click()

  // The headline reports it: a filter that hides invisibly is B30's defect shipped as a feature.
  await expect(page.getByRole('button', { name: /Filter · 1 excluded/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset' })).toBeVisible()
  await expect(page).toHaveURL(/[?&]hide=/)
  await expect
    .poll(async () => page.locator('svg g.graph-node').count())
    .toBeLessThan(before)
  expect(value).not.toBe('')
})

test('a filtered graph is a link, and reset returns the whole picture', async ({ page }) => {
  await page.goto(GRAPH)
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  const before = await page.locator('svg g.graph-node').count()
  await page.getByRole('group', { name: 'Entity type' }).getByRole('button').first().click()
  await expect(page).toHaveURL(/[?&]hide=/)
  const filtered = page.url()

  // Somebody else opening the link sees the same filtered graph, without touching the control.
  await page.goto(filtered)
  await expect(page.getByRole('button', { name: /Filter · 1 excluded/ })).toBeVisible()
  await expect.poll(async () => page.locator('svg g.graph-node').count()).toBeLessThan(before)

  await page.getByRole('button', { name: 'Reset' }).click()

  await expect(page).not.toHaveURL(/[?&]hide=/)
  await expect.poll(async () => page.locator('svg g.graph-node').count()).toBe(before)
})
