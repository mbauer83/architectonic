import { test, expect } from './coverage-fixture'

/**
 * Viewpoint execution UX: a shipped default definition executes and renders a non-empty
 * population, and a parameterized definition prompts for typed inputs (rather than
 * failing with an opaque missing-parameter error) before its first execution.
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
    localStorage.setItem('arch_group_diagram-collection', 'uncategorized')
    localStorage.setItem('arch_group_document-collection', 'uncategorized')
  })
})

test.describe('shipped default executes non-empty', () => {
  test('a shipped exploration-representation definition renders at least one entity', async ({ page }) => {
    await page.goto('/graph?viewpoint=capability-map')
    await expect(page.getByText(/entities?:\s*\d+/i)).toBeVisible({ timeout: 15000 })
    const nodeCount = await page.locator('.graph-svg .graph-node').count()
    expect(nodeCount).toBeGreaterThan(0)
  })

  test('the cluster layout spreads a multi-group population across more than one row instead of one long line', async ({ page }) => {
    await page.goto('/graph?viewpoint=goal-realization')
    await expect(page.getByText(/entities?:\s*\d+/i)).toBeVisible({ timeout: 15000 })
    const nodes = page.locator('.graph-svg .graph-node')
    await expect(nodes.first()).toBeVisible()
    const ys = await nodes.evaluateAll((els) =>
      els.map((el) => Number(el.getAttribute('transform')?.match(/,\s*([-\d.]+)\)/)?.[1])))
    expect(new Set(ys).size).toBeGreaterThan(1)
  })
})

test.describe('a non-exploration definition redirects off the graph explorer', () => {
  test('selecting a diagram-representation viewpoint on /graph redirects to the diagram surface', async ({ page }) => {
    await page.goto('/graph?viewpoint=application-structure')
    // Identity in the path since 0.2.0: `/viewpoints/{slug}/diagram`, not `?viewpoint=`.
    await expect(page).toHaveURL(/\/viewpoints\/application-structure\/diagram$/)
    await expect(page.getByRole('heading', { name: /Application Structure \(application-structure\) — diagram/ })).toBeVisible()
  })
})

test.describe('parameterized execution prompts typed inputs', () => {
  test('a definition with a required entity-id parameter shows a typed prompt, not a raw error', async ({ page }) => {
    await page.goto('/graph?viewpoint=element-dependents')
    await expect(page.getByRole('dialog', { name: 'Viewpoint parameters' })).toBeVisible()
    await expect(page.getByText('anchor (required)')).toBeVisible()
    // entity-id parameters use the entity picker, never a free-text id field.
    await expect(page.getByPlaceholder(/select an entity for anchor/i)).toBeVisible()
    // The Run button starts disabled until the required parameter has a value.
    await expect(page.getByRole('button', { name: 'Run' })).toBeDisabled()
  })

  test('cancelling the prompt returns to the unexecuted state without an error', async ({ page }) => {
    await page.goto('/graph?viewpoint=element-dependents')
    await expect(page.getByRole('dialog', { name: 'Viewpoint parameters' })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog', { name: 'Viewpoint parameters' })).toHaveCount(0)
  })
})

// Every typed execution error code has its own per-code display text unit-tested in
// viewpointExecutionErrorText.test.ts, against the published error envelope. The tests below
// cover the one thing that unit test cannot: what actually renders on screen when an
// execution call fails.

test.describe('execution failure does not show a misleading empty-result state', () => {
  test('a failed execution shows only the error banner, never the "no entities matched" diagnostics text', async ({ page }) => {
    await page.route('**/api/viewpoints/execute', (route) => route.abort('failed'))
    await page.route('**/api/viewpoints/execute-projection', (route) => route.abort('failed'))
    await page.goto('/graph?viewpoint=element-dependents')
    await expect(page.getByRole('dialog', { name: 'Viewpoint parameters' })).toBeVisible()
    await page.getByPlaceholder(/select an entity for anchor/i).fill('Architect')
    await page.locator('[data-result]').first().click()
    await page.getByRole('button', { name: 'Run' }).click()
    await expect(page.getByText('Execution failed')).toBeVisible()
    await expect(page.getByText(/No entities in the current model match/i)).toHaveCount(0)
  })
})

// A rejected parameter, refused by the REAL backend and rendered by the REAL client.
//
// This is the case the mocked block below cannot be trusted for, and the reason it exists: for a
// whole release the mocked tests injected a `{code, path, message}` body the wire never carried,
// so all four passed while the surface they claim to cover was unreachable and a raw JSON envelope
// reached the screen. Mocking the producer proves only that the client is self-consistent.
//
// `motivation-coverage` declares a boolean parameter, and a `?param.` URL always carries a string,
// so `gaps_only=maybe` is a rejection the backend genuinely produces — no interception anywhere.
test.describe('a parameter the backend rejects reaches the screen as its own state', () => {
  test('a wrong-typed URL parameter renders the typed banner, not a JSON blob', async ({ page }) => {
    await page.goto('/entities?viewpoint=motivation-coverage&param.gaps_only=maybe')
    await expect(page.getByText('A parameter was not accepted')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/parameter: gaps_only/)).toBeVisible()
    // The regression this whole surface exists for: the raw envelope on screen.
    await expect(page.getByText(/"request_id"|"field_errors"/)).toHaveCount(0)
  })
})

// Each typed execution error code renders its own distinct, actionable title — not the generic
// "Execution failed" fallback the network-abort test above exercises. The per-code prose itself is
// unit-tested in viewpointExecutionErrorText.test.ts; these prove the code reaches the screen
// through an execution round-trip.
//
// The codes below are ones a shipped definition cannot be made to produce on demand (a budget
// overrun, a binding that resolves to the wrong count), so they are injected — but the shape of
// every injected body is first checked against a refusal the REAL backend produced, in beforeAll.
// A mock the server could not have sent is a mock of nothing, and that is exactly what the
// previous version of this block was: it injected `{code, path, message}`, a body no route has
// ever returned. The e2e specs are their own TypeScript program, so the published schema cannot
// be imported here — asking the producer is both available and stronger.
test.describe('each typed execution error renders its own distinct, actionable state', () => {
  let wireKeys: readonly string[] = []

  test.beforeAll(async ({ request }) => {
    const response = await request.post('/api/viewpoints/execute', {
      data: { slug: 'motivation-coverage', parameters: { gaps_only: 'maybe' } },
    })
    expect(response.status()).toBe(400)
    const body = await response.json() as { detail: Record<string, unknown> }
    wireKeys = Object.keys(body.detail).sort()
    expect(wireKeys).toEqual(['code', 'details', 'message', 'request_id'])
  })

  const runWithTypedError = async (
    page: import('@playwright/test').Page,
    detail: Record<string, unknown>,
  ) => {
    expect(Object.keys(detail).sort(), 'the injected body is not shaped like one the server sends')
      .toEqual(wireKeys)
    const body = JSON.stringify({ detail })
    await page.route('**/api/viewpoints/execute', (route) => route.fulfill({ status: 400, contentType: 'application/json', body }))
    await page.route('**/api/viewpoints/execute-projection', (route) => route.fulfill({ status: 400, contentType: 'application/json', body }))
    await page.goto('/graph?viewpoint=element-dependents')
    await expect(page.getByRole('dialog', { name: 'Viewpoint parameters' })).toBeVisible()
    await page.getByPlaceholder(/select an entity for anchor/i).fill('Architect')
    await page.locator('[data-result]').first().click()
    await page.getByRole('button', { name: 'Run' }).click()
  }

  //: `request_id` is required by `ErrorBody`, so a body omitting it does not decode and the banner
  //: silently falls back to the generic message.
  const REQUEST_ID = '00000000000000000000000000000000'

  test('traversal_time_budget_exceeded', async ({ page }) => {
    await runWithTypedError(page, {
      code: 'traversal_time_budget_exceeded',
      message: 'The traversal exceeded its time budget.',
      details: null,
      request_id: REQUEST_ID,
    })
    await expect(page.getByText('The traversal exceeded its budget')).toBeVisible()
    await expect(page.getByText(/Narrow the query/)).toBeVisible()
  })

  test('binding_cardinality_violation', async ({ page }) => {
    await runWithTypedError(page, {
      code: 'binding_cardinality_violation',
      message: 'A binding resolved to the wrong number of items.',
      details: { binding: 'anchor', expected: 'exactly one', found: 3 },
      request_id: REQUEST_ID,
    })
    await expect(page.getByText('A binding matched the wrong number of items')).toBeVisible()
    // The binding name is the actionable part — a query may declare several.
    await expect(page.getByText(/Binding “anchor” declared exactly one and resolved to 3/)).toBeVisible()
  })

  test('validation_error naming the query', async ({ page }) => {
    await runWithTypedError(page, {
      code: 'validation_error',
      message: 'query: unknown key(s).',
      details: { field_errors: [{ field: 'query', message: 'query: unknown key(s).' }] },
      request_id: REQUEST_ID,
    })
    await expect(page.getByText('That query was not accepted')).toBeVisible()
  })

  test('validation_error naming the presentation', async ({ page }) => {
    await runWithTypedError(page, {
      code: 'validation_error',
      message: 'presentation: unknown column source.',
      details: { field_errors: [{ field: 'presentation', message: 'presentation: unknown column source.' }] },
      request_id: REQUEST_ID,
    })
    await expect(page.getByText('That presentation was not accepted')).toBeVisible()
  })

  test('an unrecognized code falls back to the generic banner rather than a JSON blob', async ({ page }) => {
    await runWithTypedError(page, {
      code: 'conflict',
      message: 'Something the client has no per-code state for.',
      details: null,
      request_id: REQUEST_ID,
    })
    await expect(page.getByText('Execution failed')).toBeVisible()
    await expect(page.getByText('Something the client has no per-code state for.')).toBeVisible()
  })
})
