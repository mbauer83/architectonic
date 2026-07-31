import { type APIRequestContext } from '@playwright/test'
import { test, expect } from './coverage-fixture'
import { findEntry } from './viewpointCatalog'

/**
 * Viewpoint query builder: named bindings (entity + connection selections), parameters,
 * derived attributes, and the extended comparator vocabulary (not_in/like/ilike) — all
 * authored entirely through GUI controls, no formula/text escape hatch.
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
    localStorage.setItem('arch_group_diagram-collection', 'uncategorized')
    localStorage.setItem('arch_group_document-collection', 'uncategorized')
  })
})

// Every minted slug is registered and swept in afterEach — cleanup must survive a
// mid-test failure, or aborted runs strand test rows in the engagement catalog.
const createdSlugs: string[] = []
const uniqueSlug = (label: string) => {
  const slug = `viewpoint-query-builder-e2e-${label}-${Date.now()}`
  createdSlugs.push(slug)
  return slug
}

test.afterEach(async ({ request }) => {
  for (const slug of createdSlugs.splice(0)) {
    await request.delete(`/api/viewpoints/${encodeURIComponent(slug)}`)
  }
})

const removeViewpoint = async (request: APIRequestContext, slug: string) => {
  await request.delete(`/api/viewpoints/${encodeURIComponent(slug)}`)
}

test.describe('bindings, parameters, and derived attributes authored entirely in the GUI', () => {
  test('an entity binding, a connection binding, a parameter, and a derived attribute all round-trip through save/reload', async ({ page, request }) => {
    const slug = uniqueSlug('full-declaration')
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(slug)
    await page.getByRole('textbox', { name: 'name' }).fill('Full Declaration Test')
    await page.getByRole('button', { name: 'Query' }).click()

    // Parameter.
    await page.getByRole('button', { name: '+ Add parameter' }).click();
    (await page.getByRole('textbox', { name: 'parameter name' }).all())[0].fill('anchor')

    // Entity binding.
    await page.getByRole('button', { name: '+ Add binding' }).click()
    const bindingRows = page.locator('.binding-row')
    await bindingRows.nth(0).getByPlaceholder('binding name').fill('critical-processes')
    await bindingRows.nth(0).getByRole('radio', { name: 'entity selection' }).check()

    // Connection binding.
    await page.getByRole('button', { name: '+ Add binding' }).click()
    await bindingRows.nth(1).getByPlaceholder('binding name').fill('serving-links')
    await bindingRows.nth(1).getByRole('radio', { name: 'connection selection' }).check()

    // Derived attribute.
    await page.getByRole('button', { name: '+ Add derived attribute' }).click();
    (await page.getByRole('textbox', { name: 'attribute name' }).all())[0].fill('serving-count')

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Viewpoints' })).toBeVisible()

    const entry = await findEntry(request, slug)
    expect(entry.query.parameters).toEqual([{ name: 'anchor', type: 'string' }])
    expect(entry.query.bindings).toEqual([
      { name: 'critical-processes', result_type: 'entities[]', select: 'entities', criteria: { kind: 'group', conjunction: 'and', children: [] } },
      { name: 'serving-links', result_type: 'connections[]', select: 'connections', criteria: { kind: 'group', conjunction: 'and', children: [] } },
    ])
    expect(entry.query.derived).toEqual([{ name: 'serving-count' }])

    await removeViewpoint(request, slug)
  })
})

test.describe('extended comparator vocabulary', () => {
  test('not_in, like, and ilike are reachable and round-trip', async ({ page, request }) => {
    const slug = uniqueSlug('comparators')
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(slug)
    await page.getByRole('textbox', { name: 'name' }).fill('Comparators Test')
    await page.getByRole('button', { name: 'Query' }).click()

    // A free-text attribute keeps the comma-list text input for not_in.
    await page.getByRole('button', { name: '+ Add condition' }).first().click()
    const row = page.locator('.group-box.root > .row').first()
    await row.locator('select.attr').selectOption('name')
    await row.locator('select.cmp').selectOption('not_in')
    await row.locator('input.val').fill('alpha, beta')

    await page.getByRole('button', { name: '+ Add condition' }).first().click()
    const secondRow = page.locator('.group-box.root > .row').nth(1)
    await secondRow.locator('select.attr').selectOption('name')
    await secondRow.locator('select.cmp').selectOption('ilike')
    await secondRow.locator('input.val').fill('%gateway%')

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Viewpoints' })).toBeVisible()

    const entry = await findEntry(request, slug)
    expect(entry.query.entity_criteria.children).toEqual([
      { kind: 'condition', attribute: 'name', comparator: 'not_in', value: ['alpha', 'beta'] },
      { kind: 'condition', attribute: 'name', comparator: 'ilike', value: '%gateway%' },
    ])

    await removeViewpoint(request, slug)
  })
})

test.describe('enumerable and entity-reference value inputs', () => {
  test('an enumerable attribute offers a dropdown (eq) and a chip multi-select (in), not free text', async ({ page, request }) => {
    const slug = uniqueSlug('enum-value')
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(slug)
    await page.getByRole('textbox', { name: 'name' }).fill('Enum Value Test')
    await page.getByRole('button', { name: 'Query' }).click()

    // status is an enumerable reserved facet (draft/active/deprecated) — `in` renders
    // toggleable chips instead of a comma-separated text field.
    await page.getByRole('button', { name: '+ Add condition' }).first().click()
    const row = page.locator('.group-box.root > .row').first()
    await row.locator('select.attr').selectOption('status')
    await row.locator('select.cmp').selectOption('in')
    await expect(row.locator('input.val')).toHaveCount(0)
    await row.getByRole('button', { name: 'active', exact: true }).click()
    await row.getByRole('button', { name: 'deprecated', exact: true }).click()

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Viewpoints' })).toBeVisible()

    const entry = await findEntry(request, slug)
    expect(entry.query.entity_criteria.children).toEqual([
      { kind: 'condition', attribute: 'status', comparator: 'in', value: ['active', 'deprecated'] },
    ])

    await removeViewpoint(request, slug)
  })

  test('the reserved id path uses the entity picker rather than a text value field', async ({ page }) => {
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(uniqueSlug('id-picker'))
    await page.getByRole('textbox', { name: 'name' }).fill('Id Picker Test')
    await page.getByRole('button', { name: 'Query' }).click()

    await page.getByRole('button', { name: '+ Add condition' }).first().click()
    const row = page.locator('.group-box.root > .row').first()
    await row.locator('select.attr').selectOption('id')
    await expect(row.locator('input[placeholder="select an entity"]')).toBeVisible()
    await expect(row.locator('input.val')).toHaveCount(0)
  })
})

test.describe('path-addressed validation into the new panels', () => {
  test('a duplicate binding name highlights the offending binding row, not just a flat error string', async ({ page }) => {
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(uniqueSlug('dup-binding'))
    await page.getByRole('textbox', { name: 'name' }).fill('Duplicate Binding Test')
    await page.getByRole('button', { name: 'Query' }).click()

    await page.getByRole('button', { name: '+ Add binding' }).click()
    await page.getByRole('button', { name: '+ Add binding' }).click()
    const bindingRows = page.locator('.binding-row')
    await bindingRows.nth(0).getByPlaceholder('binding name').fill('same-name')
    await bindingRows.nth(1).getByPlaceholder('binding name').fill('same-name')

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByText(/duplicate-binding-name/i)).toBeVisible()
    await expect(page.locator('.binding-row.highlighted')).toHaveCount(1)
  })
})

test.describe('derived-traversal authoring on neighbor inclusions and connections', () => {
  test('traversal, include-potential, and max-hops all round-trip through save/reload', async ({ page, request }) => {
    const slug = uniqueSlug('traversal')
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(slug)
    await page.getByRole('textbox', { name: 'name' }).fill('Traversal Test')
    await page.getByRole('button', { name: 'Query' }).click()

    await page.getByRole('button', { name: '+ Add neighbor inclusion' }).click()
    const inclusion = page.locator('.inclusion').first()
    await inclusion.locator('select.traversal-select').selectOption('derived')
    await inclusion.locator('input.include-potential-checkbox').check()
    await inclusion.locator('input.hops-input').fill('5')
    await inclusion.locator('input.hops-input').blur()

    await page.locator('select.conn-traversal-select').selectOption('both')
    await page.locator('input.include-potential-checkbox').last().check()
    await page.locator('input.hops-input').last().fill('5')
    await page.locator('input.hops-input').last().blur()

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Viewpoints' })).toBeVisible()

    const entry = await findEntry(request, slug)
    expect(entry.query.include_connected).toHaveLength(1)
    expect(entry.query.include_connected?.[0]).toMatchObject({ traversal: 'derived', include_potential: true, max_hops: 5 })
    expect(entry.query.connections).toMatchObject({ traversal: 'both', include_potential: true, max_hops: 5 })

    await removeViewpoint(request, slug)
  })

  test("a direct-only neighbor inclusion hides include-potential and max-hops controls, since 'both' is not offered for inclusions", async ({ page }) => {
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(uniqueSlug('direct-only'))
    await page.getByRole('textbox', { name: 'name' }).fill('Direct Only Test')
    await page.getByRole('button', { name: 'Query' }).click()

    await page.getByRole('button', { name: '+ Add neighbor inclusion' }).click()
    const inclusion = page.locator('.inclusion').first()
    await expect(inclusion.locator('select.traversal-select')).toHaveValue('direct')
    await expect(inclusion.locator('input.include-potential-checkbox')).toHaveCount(0)
    await expect(inclusion.locator('input.hops-input')).toHaveCount(0)

    const traversalOptions = await inclusion.locator('select.traversal-select option').allTextContents()
    expect(traversalOptions.join(' ')).not.toContain('direct and derived')
  })
})
