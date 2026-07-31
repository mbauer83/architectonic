import { type APIRequestContext } from '@playwright/test'
import { test, expect } from './coverage-fixture'
import { findEntry } from './viewpointCatalog'

/**
 * Viewpoint definition editor: full authoring lifecycle (create/edit/delete, semantic vs
 * descriptive edits, path-addressed validation errors) plus the scope picker's
 * hierarchy-aware include/exclude modes, chips, type-ahead, and domain bulk actions.
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
  const slug = `viewpoint-editor-e2e-${label}-${Date.now()}`
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

const createViewpoint = async (request: APIRequestContext, definition: Record<string, unknown>) => {
  const resp = await request.post('/api/viewpoints', { data: { definition, dry_run: false } })
  const body = await resp.json()
  expect(body.ok, JSON.stringify(body)).toBe(true)
  return body
}

const getCatalog = async (request: APIRequestContext) => {
  const resp = await request.get('/api/viewpoints/criteria-catalog')
  return resp.json()
}

test.describe('create/edit lifecycle with scope + query round-trip', () => {
  test('restricted scope + query condition round-trips exactly through save/reload', async ({ page, request }) => {
    const slug = uniqueSlug('roundtrip')
    const catalog = await getCatalog(request)
    const motivationTypes = Object.entries(catalog.entity_type_domains as Record<string, string>)
      .filter(([, domain]) => domain === 'motivation')
      .map(([type]) => type)
      .sort()
    expect(motivationTypes.length).toBeGreaterThan(0)

    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(slug)
    await page.getByRole('textbox', { name: 'name' }).fill('Roundtrip Test')

    await page.getByRole('button', { name: 'Scope' }).click()
    await page.getByRole('radio', { name: 'Include only selected entity types' }).click()
    const motivationGroup = page.locator('fieldset', { hasText: 'Entity types' }).locator('div', { hasText: 'motivation' }).first()
    await motivationGroup.getByRole('button', { name: 'Include all of this domain' }).click()
    await expect(page.getByText(`${motivationTypes.length} type(s) included`)).toBeVisible()

    await page.getByRole('button', { name: 'Query' }).click()
    await page.getByRole('button', { name: '+ Add condition' }).first().click()
    const conditionRow = page.locator('.group-box.root > .row').first()
    await conditionRow.locator('select.attr').selectOption('domain')
    // `domain` is an enumerable reserved facet — its value is a dropdown, not free text.
    await conditionRow.locator('select.val').selectOption('motivation')

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('button', { name: '+ Create viewpoint' })).toBeVisible()
    await expect(page.locator('tr', { hasText: slug })).toBeVisible()

    const entry = await findEntry(request, slug)
    expect(entry.scope).toEqual({ entity_types: motivationTypes })
    // `negate: false` is the wire-format default and is elided entirely, not written as `false`.
    expect(entry.query.entity_criteria.children).toEqual([
      { kind: 'condition', attribute: 'domain', comparator: 'eq', value: 'motivation' },
    ])

    await page.reload()
    const reloadedEntry = await findEntry(request, slug)
    expect(reloadedEntry.scope).toEqual(entry.scope)
    expect(reloadedEntry.query).toEqual(entry.query)

    await removeViewpoint(request, slug)
  })
})

test.describe('semantic vs descriptive edits', () => {
  test('descriptive-only edit stays quiet; a semantic edit surfaces the version-bump hint', async ({ page, request }) => {
    const slug = uniqueSlug('semantic-edit')
    await createViewpoint(request, {
      slug, version: 1, name: 'Semantic Edit Test',
      query: { query_schema: 1, entity_criteria: { kind: 'group', conjunction: 'and', children: [] } },
    })

    await page.goto('/viewpoints')
    await page.locator('tr', { hasText: slug }).getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('textbox', { name: 'description' }).fill('now described')
    await expect(page.getByText(/semantic edit/i)).toHaveCount(0)

    await page.getByRole('button', { name: 'Scope' }).click()
    await page.getByRole('radio', { name: 'Include only selected entity types' }).click()
    await expect(page.getByText(/semantic edit/i)).toBeVisible()

    // Back with unsaved edits must prompt before discarding (accept = discard).
    page.once('dialog', (dialog) => void dialog.accept())
    await page.getByRole('button', { name: '← Back' }).click()
    await removeViewpoint(request, slug)
  })
})

test.describe('path-addressed validation errors', () => {
  test('an invalid query condition highlights its own row, not just a flat error string', async ({ page }) => {
    const invalidCriteria = {
      kind: 'group', conjunction: 'and',
      children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'not-a-real-entity-type', negate: false }],
    }
    await page.goto(`/viewpoints?seedEntityCriteria=${encodeURIComponent(JSON.stringify(invalidCriteria))}`)
    await page.getByRole('textbox', { name: 'slug' }).fill(uniqueSlug('invalid-query'))
    await page.getByRole('textbox', { name: 'name' }).fill('Invalid Query Test')

    await page.getByRole('button', { name: 'Query' }).click()
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByText(/unknown attribute|not a known slug/i)).toBeVisible()
    await expect(page.locator('.group-box.root > .row.highlighted')).toHaveCount(1)
  })
})

test.describe('non-engagement tiers are read-only', () => {
  test('viewing a module-tier definition shows no Save button and explains why', async ({ page }) => {
    await page.goto('/viewpoints')
    await page.locator('tr', { hasText: 'capability-map' }).getByRole('button', { name: 'Customize…' }).click()
    await expect(page.getByText(/module-tier definition and cannot be changed in place/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Save as…', exact: true })).toBeVisible()
  })
})

test.describe('delete lifecycle', () => {
  test('deleting a definition referenced by a diagram is blocked with an actionable referencer list', async ({ page, request }) => {
    const slug = uniqueSlug('referenced')
    await createViewpoint(request, { slug, version: 1, name: 'Referenced Test' })

    const entitiesResp = await request.get('/api/entities?limit=1')
    const anyEntityId = (await entitiesResp.json()).items[0].artifact_id as string
    const diagramResp = await request.post('/api/diagrams', {
      data: {
        diagram_type: 'archimate-motivation', name: 'Viewpoint Editor E2E Referencer',
        entity_ids: [anyEntityId], connection_ids: [], viewpoint: { slug, version: 1 }, dry_run: false,
      },
    })
    const diagramBody = await diagramResp.json()
    expect(diagramBody.wrote, JSON.stringify(diagramBody)).toBe(true)
    const diagramId = diagramBody.artifact_id as string

    try {
      await page.goto('/viewpoints')
      page.once('dialog', (dialog) => void dialog.accept())
      await page.locator('tr', { hasText: slug }).getByRole('button', { name: 'Delete' }).click()
      await expect(page.getByText(`Can't delete '${slug}'`)).toBeVisible()
      await expect(page.getByRole('button', { name: new RegExp(diagramId) })).toBeVisible()
      await expect(page.locator('tr', { hasText: slug })).toBeVisible()
    } finally {
      await request.delete(`/api/diagrams/${encodeURIComponent(diagramId)}?dry_run=false`)
      await removeViewpoint(request, slug)
    }
  })
})

test.describe('query tab renders for every shipped definition', () => {
  test('every catalog definition shows a non-blank criteria tree; a query-less draft shows the empty state', async ({ page, request }) => {
    await page.goto('/viewpoints')
    const listResp = await request.get('/api/viewpoints')
    const definitions = (await listResp.json()).viewpoints as { slug: string }[]
    expect(definitions.length).toBeGreaterThan(0)

    for (const def of definitions) {
      const row = page.locator('tr').filter({ hasText: `(${def.slug})` })
      await row.getByRole('button', { name: /^(Edit|Customize…)$/ }).click()
      await page.getByRole('button', { name: 'Query' }).click()
      await expect(page.getByText('Scope-only viewpoint', { exact: false })).toHaveCount(0)
      await expect(page.getByRole('heading', { name: 'Show entities where…' })).toBeVisible()
      await page.getByRole('button', { name: '← Back' }).click()
    }

    const slug = uniqueSlug('scope-only')
    await createViewpoint(request, { slug, version: 1, name: 'Scope Only Test' })
    await page.reload()
    await page.locator('tr', { hasText: slug }).getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('button', { name: 'Query' }).click()
    await expect(page.getByText('Scope-only viewpoint — executes via its concept scope. Add a query to refine.')).toBeVisible()
    await removeViewpoint(request, slug)
  })
})

test.describe('scope picker keyboard operability', () => {
  test('type-ahead, mode switching, domain bulk action, per-type override, and chip removal all work via keyboard', async ({ page }) => {
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('button', { name: 'Scope' }).click()

    // Native radio-group arrow-key navigation moves focus+checked together starting from
    // whichever radio is currently focused, so start from the first radio in the group
    // ("Include all") rather than focusing the target directly.
    const unrestrictedRadio = page.getByRole('radio', { name: 'Include all entity types' })
    const excludeRadio = page.getByRole('radio', { name: 'Exclude selected entity types' })
    await unrestrictedRadio.focus()
    await page.keyboard.press('ArrowRight')
    await page.keyboard.press('ArrowRight')
    await expect(excludeRadio).toBeChecked()

    const searchBox = page.getByRole('searchbox', { name: 'Search entity types' })
    await searchBox.focus()
    await page.keyboard.type('application')
    await expect(page.getByRole('button', { name: 'application-component' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'business-actor' })).toHaveCount(0)

    const bulkExcludeBtn = page.getByRole('button', { name: 'Exclude all of this domain' }).first()
    await bulkExcludeBtn.focus()
    await expect(bulkExcludeBtn).toHaveCSS('outline-style', 'solid')
    await page.keyboard.press('Enter')
    const componentChip = page.getByRole('button', { name: 'application-component' })
    const interfaceChip = page.getByRole('button', { name: 'application-interface' })
    await expect(componentChip).toHaveAttribute('aria-pressed', 'true')
    await expect(interfaceChip).toHaveAttribute('aria-pressed', 'true')

    // Per-type override: carve application-interface back out of the domain exclusion.
    await interfaceChip.focus()
    await page.keyboard.press('Enter')
    await expect(interfaceChip).toHaveAttribute('aria-pressed', 'false')
    await expect(componentChip).toHaveAttribute('aria-pressed', 'true')

    // Keyboard chip removal: Delete on an unselected chip is a no-op; on a selected one it removes.
    await interfaceChip.focus()
    await page.keyboard.press('Delete')
    await expect(interfaceChip).toHaveAttribute('aria-pressed', 'false')
    await componentChip.focus()
    await page.keyboard.press('Delete')
    await expect(componentChip).toHaveAttribute('aria-pressed', 'false')
  })

  test('a scope-picker search with zero matches shows an explicit no-matches state', async ({ page }) => {
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('button', { name: 'Scope' }).click()
    await page.getByRole('radio', { name: 'Exclude selected entity types' }).check()

    const searchBox = page.getByRole('searchbox', { name: 'Search entity types' })
    await searchBox.fill('zzz-no-such-type')
    await expect(page.getByText('No types match "zzz-no-such-type" — try a different domain or term.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'application-component' })).toHaveCount(0)

    await page.getByRole('radio', { name: 'Exclude selected connection types' }).check()
    const connectionSearchBox = page.getByRole('searchbox', { name: 'Search connection types' })
    await connectionSearchBox.fill('zzz-no-such-type')
    await expect(page.getByText('No types match "zzz-no-such-type" — try a different term.')).toBeVisible()
  })
})

test.describe('criteria builder keyboard operability', () => {
  test('Tab moves coherently through a condition row and NOT/remove are keyboard-operable', async ({ page }) => {
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('button', { name: 'Query' }).click()
    await page.getByRole('button', { name: '+ Add condition' }).first().click()

    const attrSelect = page.getByRole('combobox', { name: 'attribute' })
    const cmpSelect = page.getByRole('combobox', { name: 'comparator' })
    const notBtn = page.getByRole('button', { name: 'Negate this condition' })
    const removeBtn = page.getByRole('button', { name: 'Remove condition' })

    await attrSelect.focus()
    await expect(attrSelect).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(cmpSelect).toBeFocused()

    await notBtn.focus()
    await expect(notBtn).toHaveAttribute('aria-pressed', 'false')
    await page.keyboard.press('Enter')
    await expect(notBtn).toHaveAttribute('aria-pressed', 'true')
    await page.keyboard.press('Space')
    await expect(notBtn).toHaveAttribute('aria-pressed', 'false')

    await removeBtn.focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('.group-box.root > .row')).toHaveCount(0)
  })
})

test.describe('failed save', () => {
  test('a network error on save shows a retry affordance without losing edits', async ({ page, request }) => {
    const slug = uniqueSlug('save-retry')
    await page.goto('/viewpoints')
    await page.getByRole('button', { name: '+ Create viewpoint' }).click()
    await page.getByRole('textbox', { name: 'slug' }).fill(slug)
    await page.getByRole('textbox', { name: 'name' }).fill('Save Retry Test')

    let intercepted = false
    await page.route('**/api/viewpoints', async (route) => {
      if (route.request().method() === 'POST' && !intercepted) {
        intercepted = true
        await route.abort('failed')
        return
      }
      await route.continue()
    })

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    const retryBtn = page.getByRole('button', { name: '↻ Retry' })
    await expect(retryBtn).toBeVisible()

    // Edits are still there — the failed save never touched the draft.
    await expect(page.getByRole('textbox', { name: 'slug' })).toHaveValue(slug)
    await expect(page.getByRole('textbox', { name: 'name' })).toHaveValue('Save Retry Test')

    await retryBtn.click()
    await expect(page.getByRole('heading', { name: 'Viewpoints' })).toBeVisible()

    const entry = await findEntry(request, slug)
    expect(entry).toBeTruthy()

    await removeViewpoint(request, slug)
  })
})

test.describe('reference integrity surfacing', () => {
  test('a broken reference shows a catalogue badge and an editor notice', async ({ page, request }) => {
    const slug = uniqueSlug('broken-ref')
    // An entity-id parameter default is warning-severity (not save-blocked), so it can be
    // created directly — a nonexistent anchor is a broken reference the report must surface.
    await createViewpoint(request, {
      slug, version: 1, name: 'Broken Reference Test', selection_mode: 'query',
      query: {
        query_schema: 1,
        entity_criteria: { kind: 'group', conjunction: 'and', children: [] },
        parameters: [{ name: 'anchor', type: 'entity-id', required: false, default: 'ENT@0.does-not-exist' }],
      },
    })

    // Server computed the report on the list endpoint (never persisted, so it recomputes).
    const entry = await findEntry(request, slug)
    expect(entry.broken_references.some((b: { reference: string }) => b.reference === 'ENT@0.does-not-exist')).toBe(true)

    await page.goto('/viewpoints')
    const row = page.locator('tr', { hasText: slug })
    await expect(row.getByText(/broken reference/i)).toBeVisible()

    await row.getByRole('button', { name: 'Edit', exact: true }).click()
    await expect(page.getByText(/no longer (resolve|resolves) against the current model/i)).toBeVisible()
    await expect(page.getByText('ENT@0.does-not-exist')).toBeVisible()

    page.once('dialog', (dialog) => void dialog.accept())
    await page.getByRole('button', { name: '← Back' }).click()
    await removeViewpoint(request, slug)
  })
})
