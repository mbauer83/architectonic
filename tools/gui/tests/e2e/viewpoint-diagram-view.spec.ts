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
  await page.goto('/viewpoints/diagram?viewpoint=technology-usage')
  await expect(page.getByText(/entities:\s*\d+/i)).toBeVisible({ timeout: 15000 })

  const container = page.locator('.img-container')
  await expect(container).toBeVisible()
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
  await page.goto('/viewpoints/diagram?viewpoint=application-structure')
  await expect(page.getByText(/entities:\s*\d+/i)).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.img-container')).toBeVisible()
  await expect(page.locator('.sb-title', { hasText: 'Entities' })).toBeVisible()
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
    await request.post('/api/viewpoints/remove', { data: { slug: 'diagram-view-derived-e2e', dry_run: false } })
  })

  test('a derived connection arrow is selectable and shows its witness chain in the sidebar', async ({ page }) => {
    await page.goto('/viewpoints/diagram?viewpoint=diagram-view-derived-e2e')
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
