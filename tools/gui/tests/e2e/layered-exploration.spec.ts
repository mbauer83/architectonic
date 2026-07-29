import { test, expect } from './coverage-fixture'

/**
 * The layered-exploration and motivation-support flows: build an ephemeral (never saved)
 * view by selecting roots (by name/id, or by criteria) and pulling in indirectly-connected
 * neighbors of a chosen kind, with no YAML/formula/text query input anywhere. Execution
 * responses are mocked (matching the real backend's documented wire shape) so the
 * assertions are deterministic regardless of what derivable chains happen to exist in the
 * real dogfood repo at test time; the mocked shape itself is proven correct elsewhere
 * (viewpoints.test.ts's schema-decode regression test, and this session's live
 * verification against the real backend).
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
  })
})

const ROOT_ID = 'PRC@test.9AbC12.root-process'
const TECH_ID = 'NOD@test.3XyZ99.tech-node'
const CONN_A = 'CON@test.aaa'
const CONN_B = 'CON@test.bbb'
const CONN_C = 'CON@test.ccc'

const executionResult = (overrides: Partial<Record<string, unknown>> = {}) => ({
  slug: null, version: null, query_schema: 1, repo_scope: 'both', executed_at: '2026-07-13T00:00:00Z',
  index_generation: 1,
  entity_ids: [ROOT_ID, TECH_ID],
  connection_ids: ['derived::archimate-association::x'],
  entities: [
    { id: ROOT_ID, name: 'Root Process', type: 'process', specialization_slugs: ['business-process'], group: 'platform-core', membership: 'primary' },
    { id: TECH_ID, name: 'Tech Node', type: 'technology-node', specialization_slugs: [], group: 'platform-core', membership: 'expanded' },
  ],
  connections: [
    {
      id: 'derived::archimate-association::x', type: 'archimate-association', source: TECH_ID, target: ROOT_ID,
      certainty: 'potential', hops: 3, via_connection_ids: [CONN_A, CONN_B, CONN_C],
    },
  ],
  total_entity_count: 2, returned_entity_count: 2, total_connection_count: 1, returned_connection_count: 1,
  truncated: false, entity_limit: 500, matrix_axes: null, warnings: [], duration_ms: 12.3,
  query_summary: 'mocked', ...overrides,
})

const projectionResult = () => ({ applied: true, target: 'repository', items: [], warnings: [] })

test.describe('layered view: quality flow', () => {
  test('selecting a root by name/id renders only the selected element plus its indirectly connected technology neighbor, and a derived arrow shows witness-chain prose with clickable entity links', async ({ page }) => {
    await page.route('**/api/entity-display-search*', (route) =>
      route.fulfill({ json: { items: [{
        artifact_id: ROOT_ID, name: 'Root Process', artifact_type: 'process', domain: 'business',
        subdomain: '', status: 'active', display_alias: 'Root Process', element_type: 'process', element_label: 'Process',
      }], next_cursor: null } }))
    await page.route('**/api/entity-display-item*', (route) =>
      route.fulfill({ json: {
        artifact_id: ROOT_ID, name: 'Root Process', artifact_type: 'process', domain: 'business',
        subdomain: '', status: 'active', display_alias: 'Root Process', element_type: 'process', element_label: 'Process',
      } }))
    await page.route('**/api/viewpoints/execute', (route) => route.fulfill({ json: executionResult() }))
    await page.route('**/api/viewpoints/execute-projection', (route) => route.fulfill({ json: projectionResult() }))
    await page.route(`**/api/connections?entity_id=${encodeURIComponent(TECH_ID)}*`, (route) =>
      route.fulfill({ json: [{
        artifact_id: CONN_A, source: TECH_ID, target: 'ENT@test.hop1', conn_type: 'archimate-serving',
        version: '1', status: 'active', path: '', content_text: '', source_name: 'Tech Node', target_name: 'Hop One',
      }] }))
    await page.route(`**/api/connections?entity_id=${encodeURIComponent('ENT@test.hop1')}*`, (route) =>
      route.fulfill({ json: [
        {
          artifact_id: CONN_A, source: TECH_ID, target: 'ENT@test.hop1', conn_type: 'archimate-serving',
          version: '1', status: 'active', path: '', content_text: '', source_name: 'Tech Node', target_name: 'Hop One',
        },
        {
          artifact_id: CONN_B, source: 'ENT@test.hop1', target: 'ENT@test.hop2', conn_type: 'archimate-composition',
          version: '1', status: 'active', path: '', content_text: '', source_name: 'Hop One', target_name: 'Hop Two',
        },
      ] }))
    await page.route(`**/api/connections?entity_id=${encodeURIComponent('ENT@test.hop2')}*`, (route) =>
      route.fulfill({ json: [
        {
          artifact_id: CONN_B, source: 'ENT@test.hop1', target: 'ENT@test.hop2', conn_type: 'archimate-composition',
          version: '1', status: 'active', path: '', content_text: '', source_name: 'Hop One', target_name: 'Hop Two',
        },
        {
          artifact_id: CONN_C, source: 'ENT@test.hop2', target: ROOT_ID, conn_type: 'archimate-association',
          version: '1', status: 'active', path: '', content_text: '', source_name: 'Hop Two', target_name: 'Root Process',
        },
      ] }))
    await page.route(`**/api/connections?entity_id=${encodeURIComponent(ROOT_ID)}*`, (route) =>
      route.fulfill({ json: [{
        artifact_id: CONN_C, source: 'ENT@test.hop2', target: ROOT_ID, conn_type: 'archimate-association',
        version: '1', status: 'active', path: '', content_text: '', source_name: 'Hop Two', target_name: 'Root Process',
      }] }))

    await page.goto('/graph/layered')
    await expect(page.getByRole('heading', { name: 'Build a layered view' })).toBeVisible()
    // No YAML or free-text query input anywhere on the page.
    await expect(page.locator('textarea')).toHaveCount(0)

    await page.getByPlaceholder('Search entities to add as roots…').fill('Root')
    await expect(page.locator('[data-result]').first()).toBeVisible()
    await page.locator('[data-result]').first().click()
    await expect(page.locator('.root-chip')).toContainText('Root Process')
    await page.getByRole('heading', { name: 'Build a layered view' }).click()
    await page.getByRole('button', { name: 'Render' }).click()

    await expect(page.locator('.rendered-entities')).toContainText('Root Process')
    await expect(page.locator('.rendered-entities')).toContainText('Tech Node')
    const renderedItems = await page.locator('.rendered-entities li').allTextContents()
    expect(renderedItems.sort()).toEqual(['Root Process', 'Tech Node'])

    await page.getByRole('button', { name: 'Explain' }).click()
    const dialog = page.getByRole('dialog', { name: 'Witness chain' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('link', { name: 'Tech Node' })).toBeVisible()
    await expect(dialog.getByRole('link', { name: 'Hop One' })).toBeVisible()
    await expect(dialog.getByRole('link', { name: 'Hop Two' })).toBeVisible()
    await expect(dialog.getByRole('link', { name: 'Root Process' })).toBeVisible()
  })

  test('selecting roots by criteria (instead of by name/id) reaches the same execution path', async ({ page }) => {
    await page.route('**/api/viewpoints/execute', (route) => route.fulfill({ json: executionResult() }))
    await page.route('**/api/viewpoints/execute-projection', (route) => route.fulfill({ json: projectionResult() }))

    await page.goto('/graph/layered')
    await page.getByRole('button', { name: 'By criteria' }).click()
    // The criteria builder replaces the picker — still no free-text query input.
    await expect(page.locator('textarea')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Render' })).toBeEnabled()
    await page.getByRole('button', { name: 'Render' }).click()
    await expect(page.locator('.rendered-entities')).toContainText('Root Process')
  })
})

test.describe('stale-finding review after a re-run', () => {
  test('a previously-accepted candidate that no longer derives is listed individually and can be re-reviewed or removed', async ({ page }) => {
    let call = 0
    await page.route('**/api/viewpoints/execute', (route) => {
      call += 1
      const result = call === 1
        ? executionResult({
            connections: [{
              id: 'derived::archimate-association::x', type: 'archimate-association', source: TECH_ID, target: ROOT_ID,
              certainty: 'certain', hops: 2, via_connection_ids: [CONN_A, CONN_B],
            }],
          })
        : executionResult({ connections: [] })
      return route.fulfill({ json: result })
    })
    await page.route('**/api/viewpoints/execute-projection', (route) => route.fulfill({ json: projectionResult() }))

    await page.goto('/graph/layered')
    await page.getByRole('button', { name: 'By criteria' }).click()
    await page.getByRole('button', { name: 'Render' }).click()
    await expect(page.locator('.rendered-entities')).toContainText('Tech Node')

    // Re-run with the same params — this time the mocked response no longer includes the
    // certain (auto-accepted) derived candidate, so it goes stale.
    await page.getByRole('button', { name: 'Render' }).click()
    await expect(page.getByText('1 previously-accepted relationship no longer derives after this re-run:')).toBeVisible()
    await expect(page.getByText('Tech Node → Root Process (archimate-association)')).toBeVisible()

    await page.getByRole('button', { name: 'Re-review' }).click()
    await expect(page.getByRole('dialog', { name: 'Witness chain' })).toBeVisible()
    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.getByRole('dialog', { name: 'Witness chain' })).toHaveCount(0)

    await page.getByRole('button', { name: 'Remove', exact: true }).click()
    await expect(page.getByText(/previously-accepted relationship/)).toHaveCount(0)
  })
})

test.describe('motivation-support flow', () => {
  // A single goal's indirect support spanning three different domains — business (a
  // process), application (a service), and common (a function) — to prove the
  // "process/function/event/service/application" neighbor-type criteria genuinely spans
  // domains rather than only ever surfacing whatever one domain a narrower fixture would
  // happen to exercise.
  const BUSINESS_ID = 'PRC@test.biz1.supporting-process'
  const APPLICATION_ID = 'SVC@test.app1.supporting-application-service'
  const COMMON_ID = 'FNC@test.com1.supporting-function'

  test('selecting a goal renders indirect supporting elements across business, application, and common domains; toggling certainty inclusion and the legend distinguish certain from potential', async ({ page }) => {
    await page.route('**/api/entity-display-search*', (route) =>
      route.fulfill({ json: { items: [{
        artifact_id: ROOT_ID, name: 'A Goal', artifact_type: 'goal', domain: 'motivation',
        subdomain: '', status: 'active', display_alias: 'A Goal', element_type: 'goal', element_label: 'Goal',
      }], next_cursor: null } }))
    await page.route('**/api/entity-display-item*', (route) =>
      route.fulfill({ json: {
        artifact_id: ROOT_ID, name: 'A Goal', artifact_type: 'goal', domain: 'motivation',
        subdomain: '', status: 'active', display_alias: 'A Goal', element_type: 'goal', element_label: 'Goal',
      } }))
    await page.route('**/api/viewpoints/execute', (route) => route.fulfill({ json: executionResult({
      entities: [
        { id: ROOT_ID, name: 'A Goal', type: 'goal', specialization_slugs: [], group: 'platform-core', membership: 'primary' },
        { id: BUSINESS_ID, name: 'Supporting Process', type: 'business-process', specialization_slugs: [], group: 'platform-core', membership: 'expanded' },
        { id: APPLICATION_ID, name: 'Supporting Application Service', type: 'application-service', specialization_slugs: [], group: 'platform-core', membership: 'expanded' },
        { id: COMMON_ID, name: 'Supporting Function', type: 'function', specialization_slugs: ['business-function'], group: 'platform-core', membership: 'expanded' },
      ],
      connections: [
        {
          id: 'derived::archimate-realization::biz', type: 'archimate-realization', source: BUSINESS_ID, target: ROOT_ID,
          certainty: 'certain', hops: 2, via_connection_ids: [CONN_A],
        },
        {
          id: 'derived::archimate-realization::app', type: 'archimate-realization', source: APPLICATION_ID, target: ROOT_ID,
          certainty: 'potential', hops: 3, via_connection_ids: [CONN_B],
        },
        {
          id: 'derived::archimate-association::com', type: 'archimate-association', source: COMMON_ID, target: ROOT_ID,
          certainty: 'potential', hops: 3, via_connection_ids: [CONN_C],
        },
      ],
    }) }))
    await page.route('**/api/viewpoints/execute-projection', (route) => route.fulfill({ json: projectionResult() }))

    await page.goto('/graph/layered')
    await page.getByRole('button', { name: 'Motivation support' }).click()
    await expect(page.getByText('Requirement / motivation element:')).toBeVisible()

    await page.getByPlaceholder('Search entities to add as roots…').fill('Goal')
    await expect(page.locator('[data-result]').first()).toBeVisible()
    await page.locator('[data-result]').first().click()
    await expect(page.locator('.root-chip')).toContainText('A Goal')
    await page.getByRole('heading', { name: 'Build a layered view' }).click()
    await page.getByRole('checkbox', { name: 'Include potential (uncertain' }).click()
    await page.getByRole('button', { name: 'Render' }).click()

    // All three domains' supporting elements render — not just whichever one domain a
    // narrower fixture would have exercised.
    const renderedItems = await page.locator('.rendered-entities li').allTextContents()
    expect(renderedItems.sort()).toEqual([
      'A Goal', 'Supporting Application Service', 'Supporting Function', 'Supporting Process',
    ])

    // Legend distinguishes certain from potential.
    await expect(page.locator('.legend')).toContainText('Certain')
    await expect(page.locator('.legend')).toContainText('Potential')

    // Per-occurrence defaults: the one certain candidate (business) starts accepted, the
    // two potential candidates (application, common) start rejected until reviewed.
    const rows = page.locator('.candidate-row')
    await expect(rows).toHaveCount(3)
    const decisions = await rows.evaluateAll((els) =>
      els.map((el) => el.querySelector('.decision-btn')?.textContent?.trim()))
    expect(decisions.filter((d) => d === 'Accepted')).toHaveLength(1)
    expect(decisions.filter((d) => d === 'Rejected')).toHaveLength(2)
  })
})
