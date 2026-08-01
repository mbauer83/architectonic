/**
 * Relationships are drawn the way the ontology says they are drawn.
 *
 * The graph explorer rendered every ArchiMate relationship as one solid line with a filled
 * head, in every layout mode: a composition, a realization and an association were
 * indistinguishable, so the picture asserted nothing the model did not already list in text.
 *
 * The notation now comes from `connections.yaml` and reaches the canvas as *structural* shapes
 * — "hollow triangle at the target", never "realization" — so `GraphCanvas` draws them without
 * learning any ontology's vocabulary. That boundary is held by
 * `tests/architecture/test_generic_graph_module_boundaries.py`; this holds the visible result.
 */
import { expect, test, type Page } from '@playwright/test'

const ANCHOR = 'ASS@1776628134.EI3FpR.ai-generated-change-volume-outpaces-architectural-planning-and-review-capacity'

/** Marker + dash per edge, as the DOM actually carries them. */
const edgeStyles = async (page: Page): Promise<string[]> =>
  page.locator('.graph-edge path:first-child').evaluateAll((paths) => paths.map((p) => {
    const end = (attr: string) => (p.getAttribute(attr) ?? 'none')
      .replace(/url\(#edge-(source|target)-/, '').replace(')', '')
    return `${end('marker-start')}|${end('marker-end')}|${p.getAttribute('stroke-dasharray') ?? 'solid'}`
  }))

/** Walk far enough that the neighbourhood spans more than one relationship type. */
const openAndWalk = async (page: Page): Promise<void> => {
  await page.goto(`/entities/${encodeURIComponent(ANCHOR)}/graph`, { waitUntil: 'load' })
  await expect(page.locator('.graph-svg')).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState('networkidle')
  const nodes = page.locator('.graph-node')
  for (let hop = 0; hop < 2; hop++) {
    const before = await nodes.count()
    const expandable = nodes.filter({ has: page.locator('.expand-badge') })
    if (await expandable.count() <= hop) break
    await expandable.nth(hop).dispatchEvent('dblclick')
    await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
    await page.waitForLoadState('networkidle')
  }
  await page.waitForTimeout(1500)
}

test('the ontology serves a distinct notation for each relationship type', async ({ page }) => {
  // The source of the whole feature: if the ontology itself declared one shape for everything,
  // every assertion below would pass against a picture that still said nothing.
  const response = await page.request.get('/api/relation-notations')
  expect(response.ok()).toBe(true)
  const { notations } = (await response.json()) as {
    notations: Record<string, { line: string; source: string; target: string }>
  }

  const archimate = Object.entries(notations).filter(([name]) => name.startsWith('archimate-'))
  expect(archimate.length).toBeGreaterThan(4)
  const distinct = new Set(archimate.map(([, n]) => `${n.line}|${n.source}|${n.target}`))
  expect(distinct.size, 'the ontology declares one notation for everything').toBeGreaterThan(3)

  // The distinction PlantUML cannot express, and the reason `puml_arrow` is not the authority.
  expect(notations['archimate-composition']?.source).toBe('filled-diamond')
  expect(notations['archimate-aggregation']?.source).toBe('hollow-diamond')
})

test('edges render with more than one arrow shape', async ({ page }) => {
  await openAndWalk(page)

  const styles = await edgeStyles(page)
  expect(styles.length, 'no edges were drawn at all').toBeGreaterThan(3)
  expect(new Set(styles).size, `every edge rendered identically: ${styles[0]}`).toBeGreaterThan(1)
})

test('an end the ontology leaves undecorated gets no arrowhead', async ({ page }) => {
  /*
   * `none` and "said nothing" are different answers. The first version conflated them, so an
   * aggregation drew its source diamond *and* grew a filled head back at the target — a shape
   * that exists in no notation.
   */
  await openAndWalk(page)

  const styles = await edgeStyles(page)
  const withSourceDiamond = styles.filter((s) => s.startsWith('hollow-diamond|') || s.startsWith('filled-diamond|'))
  test.skip(withSourceDiamond.length === 0, 'this neighbourhood has no containment relationship')

  for (const style of withSourceDiamond) {
    expect(style, 'a diamond-sourced relationship also drew an arrowhead').toContain('|none|')
  }
})

test('line style follows the ontology, not just the arrowhead', async ({ page }) => {
  // Realization and specialization share a head and differ only in their line; a renderer that
  // honoured markers alone would still draw those two identically.
  await openAndWalk(page)

  const dashes = new Set((await edgeStyles(page)).map((s) => s.split('|')[2]))

  expect(dashes.size, `every edge used the same line style: ${[...dashes]}`).toBeGreaterThan(1)
})
