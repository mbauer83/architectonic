import { test, expect } from './coverage-fixture'

/**
 * The ad-hoc `diagram` execution representation renders through the same viewport
 * (pan/zoom, fixed-height container, resizable sidebar) and click-to-select interactivity
 * as a real persisted diagram — a large population must stay resizable/navigable rather
 * than expanding the page to its native SVG size, and entities must be selectable from a
 * sidebar exactly like `DiagramDetailView.vue`'s.
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
  })
})

test('a large viewpoint diagram renders inside a bounded, resizable viewport with a working entity sidebar', async ({ page }) => {
  // A whole-layer viewpoint over the dogfood repo, chosen for headroom under the renderer's
  // entity ceiling rather than for size alone. `technology-usage` was here and crossed that
  // ceiling as the model grew: the backend then refuses — correctly, and that refusal has a spec
  // of its own below — so this one stopped being about the viewport at all and started failing
  // for a reason it does not test.
  await page.goto('/viewpoints/motivation/diagram')
  await expect(page.getByText(/entities:\s*\d+/i)).toBeVisible({ timeout: 15000 })

  const container = page.locator('.img-container')
  // The count arrives as soon as the query resolves; the *picture* is a PlantUML render of the
  // whole population, which the page itself says "can take a while". The default 5 s was a budget
  // for the wrong operation — it held only while the machine was idle, so this failed in a full
  // suite run and passed alone.
  await expect(container).toBeVisible({ timeout: 30_000 })
  const containerBox = await container.boundingBox()
  expect(containerBox).not.toBeNull()
  // The container is clamped to a sane viewport height, never the diagram's native size.
  expect(containerBox!.height).toBeLessThan(1000)

  await expect(page.locator('.sb-title', { hasText: 'Entities' })).toBeVisible()

  const firstEntity = page.locator('.ent-list .ent-item').first()
  const entityName = (await firstEntity.textContent())?.trim()
  await firstEntity.click()
  await expect(page.locator('.det-name', { hasText: entityName ?? '' })).toBeVisible()
  await expect(page.getByText('Explore in graph')).toBeVisible()
})

test('a diagram-representation viewpoint with only a small population still shows a usable, bounded viewport', async ({ page }) => {
  await page.goto('/viewpoints/application-structure/diagram')
  await expect(page.getByText(/entities:\s*\d+/i)).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.img-container')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.sb-title', { hasText: 'Entities' })).toBeVisible()
})

test('a population past the renderer ceiling says so, and says what to do instead', async ({ page }) => {
  // The refusal is the backend's, it names the counts and the alternatives, and none of it reached
  // the reader: the diagram call's error envelope was stringified while only the *execution* call's
  // was passed to the display, so a viewpoint that had simply outgrown the renderer showed the bare
  // fallback title. Asserted on the prose rather than on any count, because which viewpoints are
  // over the ceiling is a fact about the model and changes as it grows.
  await page.goto('/viewpoints/layered/diagram')
  await expect(page.locator('.exec-error-title')).toHaveText(/too large for diagram rendering/i, { timeout: 30_000 })
  await expect(page.locator('.exec-error-detail')).toHaveText(/table representation|narrow the scope/i)
})

test.describe('derived connections', () => {
  // Mirrors the shipped `element-dependents` definition's query exactly (a single
  // entity-id anchor parameter, `traversal: derived` incoming inclusion, `max_hops: 4`) —
  // known to produce a small, fast, deterministic population against the dogfood repo —
  // but with `presentation.representation: diagram` instead of `exploration`, since this
  // spec is specifically about the diagram surface's click-to-select/witness-chain UX.
  test.beforeEach(async ({ request }) => {
    await request.post('/api/viewpoints', {
      data: {
        definition: {
          slug: 'diagram-view-derived-e2e', version: 1, name: 'Diagram View Derived E2E',
          representation_types: ['archimate-layered'],
          query: {
            query_schema: 1,
            entity_criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'id', comparator: 'eq', value: { from: 'parameter', name: 'anchor' } }] },
            include_connected: [{ direction: 'incoming', traversal: 'derived', max_hops: 4 }],
            connections: { traversal: 'both' },
            parameters: [{ name: 'anchor', type: 'entity-id', description: 'anchor entity' }],
          },
          presentation: { representation: 'diagram' },
        },
        dry_run: false,
      },
    })
  })

  test.afterEach(async ({ request }) => {
    await request.delete('/api/viewpoints/diagram-view-derived-e2e?dry_run=false')
  })

  test('a derived connection arrow is selectable and shows its witness chain in the sidebar', async ({ page }) => {
    await page.goto('/viewpoints/diagram-view-derived-e2e/diagram')
    await expect(page.getByPlaceholder(/select an entity for anchor/i)).toBeVisible()
    await page.getByPlaceholder(/select an entity for anchor/i).fill('Synthesize & Deliver Implementation Guidance')
    await page.locator('[data-result]').first().click()
    await page.getByRole('button', { name: 'Run' }).click()

    await expect(page.getByText(/entities:\s*\d+/i)).toBeVisible({ timeout: 15000 })

    // `data-certainty` (set once the style overlay applies) and `data-conn-id` (set once
    // click-to-select interactivity attaches) land via two independent async chains off the
    // same render — wait for both together, not just the style marker, or the click can
    // race ahead of the listener actually being attached. A coordinate-based `.click()`
    // (even `force: true`) hit-tests the element's bounding-box CENTER against real pixels,
    // which for a thin curved connector path can land on a visually overlapping entity
    // instead — `dispatchEvent('click')` fires directly on the resolved element, bypassing
    // hit-testing entirely, matching what the click listener itself actually responds to.
    const derivedEdge = page.locator('[data-certainty][data-conn-id]').first()
    await expect(derivedEdge).toBeVisible({ timeout: 15000 })
    await derivedEdge.dispatchEvent('click')

    await expect(page.locator('.det-derived')).toBeVisible()
    await expect(page.locator('.chain-prose')).toBeVisible()
    // At least one clickable entity link in the resolved witness chain.
    await expect(page.locator('.chain-entity').first()).toBeVisible()
  })
})
