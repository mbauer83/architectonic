import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

/**
 * The stress-analysis workspace, driven as an analyst drives it: starting an analysis from a diagram
 * and sketching its naive architecture straight away,
 * a stressor written, grouped and ticked on the canvas, an end state in focus, and a test set held out
 * of the design stressors and judged on the naive architecture.
 *
 * Each test makes its own analysis and deletes it afterwards: the document, then the naive
 * architecture it named, which the candidate delete refuses while the document still names it.
 */

const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const SERVICE_ALIAS = 'SRV_Uv9Wx9'
const ARTIFACTS_ALIAS = 'PRC_0Rz5Ex'

const created: string[] = []
const candidates: string[] = []

/** Whether the served engagement declares the stress-analysis document type (shipped as a default). */
const declaresStressAnalysis = async (request: APIRequestContext): Promise<boolean> => {
  const types = await (await request.get('/api/document-types')).json() as { document_types: { doc_type: string }[] }
  return types.document_types.some((one) => one.doc_type === 'stress-analysis')
}

interface Started { document: string; naive_candidate: { record: { id: string; changes: Record<string, unknown> }; version: string } }

/** An analysis of the diagram, started through the one write the start page makes. */
const startAnalysis = async (request: APIRequestContext, title: string): Promise<Started> => {
  const started = await request.post('/api/stress-analyses', {
    data: { title, naive: { name: 'Naive architecture', diagram: DIAGRAM } },
  })
  expect(started.ok(), await started.text()).toBe(true)
  const body = await started.json() as Started
  created.push(body.document)
  candidates.push(body.naive_candidate.record.id)
  return body
}
const analysisOf = async (request: APIRequestContext, title: string): Promise<string> =>
  (await startAnalysis(request, title)).document

const listedCandidates = async (request: APIRequestContext): Promise<string[]> =>
  ((await (await request.get('/api/change-sets')).json()) as { candidates: { id: string }[] }).candidates.map((c) => c.id)

const operationsOf = async (request: APIRequestContext, id: string): Promise<unknown[]> =>
  ((await (await request.get(`/api/change-sets/${encodeURIComponent(id)}`)).json()) as
    { record: { changes: { operations: unknown[] } } }).record.changes.operations

const workspace = (page: Page, id: string, tab: string) =>
  page.goto(`/documents/${encodeURIComponent(id)}/workspace?tab=${tab}`)

const element = (page: Page, alias: string) =>
  page.getByTestId('workspace-canvas').locator(`g.lab-element[data-alias="${alias}"] .lab-grip`)

test.beforeEach(async ({ request }) => {
  test.skip(!(await declaresStressAnalysis(request)), 'the served engagement does not declare the stress-analysis document type')
})

// A candidate delete is a dry run unless it says otherwise, as a document delete is: both ask for the
// real one, and the candidate's is checked, so a run that leaves its naive architecture behind fails here.
test.afterEach(async ({ request }) => {
  for (const id of created.splice(0)) await request.delete(`/api/documents/${encodeURIComponent(id)}?dry_run=false`)
  for (const id of candidates.splice(0)) {
    const deleted = await request.delete(`/api/change-sets/${encodeURIComponent(id)}?dry_run=false`)
    expect(deleted.status(), await deleted.text()).toBe(204)
  }
})

test('starting writes the naive architecture and the document together, and a refused start writes neither', async ({ request }) => {
  const { document, naive_candidate: naive } = await startAnalysis(request, 'Stress analysis — one write')
  const read = await (await request.get(`/api/documents/${encodeURIComponent(document)}`)).json() as { extra: Record<string, string> }
  expect(read.extra['naive-candidate']).toBe(naive.record.id)
  expect(await listedCandidates(request)).toContain(naive.record.id)

  const before = await listedCandidates(request)
  const refused = await request.post('/api/stress-analyses', {
    data: { title: 'Stress analysis — one write', naive: { name: 'A second naive' }, scope_diagram: DIAGRAM },
  })
  expect(refused.status()).toBe(422)
  expect(await listedCandidates(request)).toEqual(before)

  const named = await request.delete(`/api/change-sets/${encodeURIComponent(naive.record.id)}`)
  expect(named.status()).toBe(409)
  expect(await named.text()).toContain('naive architecture of')
})

test('the workspace says the model moved under a drifted operation, and re-basing settles it', async ({ page, request }) => {
  const { document, naive_candidate: naive } = await startAnalysis(request, 'Stress analysis — model moved')
  const scope = await (await request.get(`/api/change-sets/${encodeURIComponent(naive.record.id)}`)).json() as
    { record: { scope: string[] } }
  const service = scope.record.scope.find((ref) => ref.startsWith('SRV@')) ?? ''
  // An edit written against a name the model no longer holds: what a rename made elsewhere leaves behind.
  const drifted = { op: 'edit_entity', artifact_id: service, field: 'name', value: 'Promotion Review Service',
    base: { value: 'Promotion Service (as it was)' } }
  const edited = await request.patch(`/api/change-sets/${encodeURIComponent(naive.record.id)}`, {
    data: { based_on: naive.version, patch: { changes: { ...naive.record.changes, operations: [drifted] } } },
  })
  expect(edited.ok(), await edited.text()).toBe(true)

  await workspace(page, document, 'stressors')
  const band = page.getByTestId('model-moved')
  await expect(band).toContainText('1 operation changed in the model since it was written.')
  await band.getByRole('button', { name: 'Show them' }).click()
  await expect(band).toContainText('changed since this edit was written')
  await band.getByTestId('rebase').click()
  await expect(band).toHaveCount(0)
  const standing = await (await request.get(`/api/change-sets/${encodeURIComponent(naive.record.id)}/standing`)).json() as
    { standing: { standing: string }[] }
  expect(standing.standing.map((one) => one.standing)).toEqual(['applies'])
})

test('undo on the sketching canvas takes the recorded operation back out of the candidate', async ({ page, request }) => {
  const { document, naive_candidate: naive } = await startAnalysis(request, 'Stress analysis — undo')
  await workspace(page, document, 'naive')
  await page.getByTestId('sketch').click()
  const service = page.getByTestId('candidate-canvas').locator(`g.lab-element[data-alias="${SERVICE_ALIAS}"] .lab-grip`)
  await service.click({ button: 'right', force: true })
  await page.getByRole('dialog', { name: 'element' }).getByRole('menuitem', { name: 'Rename' }).click()
  await page.getByRole('dialog', { name: 'rename' }).getByLabel('Name').fill('Promotion Review Service')
  await page.getByRole('button', { name: 'Keep rename' }).click()
  const operations = page.getByTestId('candidate-operations').locator('tr.oprow')
  await expect(operations).toHaveCount(1)
  await expect.poll(() => operationsOf(request, naive.record.id)).toHaveLength(1)

  await page.getByTestId('undo-sketch').click()
  await expect(operations).toHaveCount(0)
  await expect.poll(() => operationsOf(request, naive.record.id)).toHaveLength(0)
})

test('starting an analysis from a diagram opens its naive architecture for sketching', async ({ page, request }) => {
  await page.goto('/stress-analyses/new')
  await expect(page.getByText('Question')).toHaveCount(0)
  await page.getByTestId('scope-diagram').selectOption(DIAGRAM)
  await expect(page.getByTestId('analysis-name')).toHaveValue(/^Stress analysis — /)
  await page.getByTestId('analysis-name').fill('Stress analysis — start flow')
  await page.getByTestId('analysis-context').fill('Promotion volumes double; the evaluation informs tiering.')
  await expect(page.getByTestId('scope-count')).not.toContainText(/^0 elements/)
  await expect(element(page, SERVICE_ALIAS)).toBeAttached()
  await page.getByTestId('start-naive').click()

  await page.waitForURL(/\/workspace\?tab=naive&sketch=naive$/)
  const document = decodeURIComponent(page.url().split('/documents/')[1].split('/workspace')[0])
  created.push(document)
  const read = await (await request.get(`/api/documents/${encodeURIComponent(document)}`)).json() as { extra: Record<string, string> }
  candidates.push(read.extra['naive-candidate'])
  await expect(page.getByRole('tab', { name: /Naive architecture/ })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('candidate-operations')).toContainText('naive architecture · the initial candidate')
  await expect(page.getByTestId('analysis-context')).toContainText('the evaluation informs tiering')
  await expect(page.getByTestId('naive-intro')).toBeVisible()
  await expect(page.getByTestId('candidate-canvas')).toBeVisible()
  await page.getByTestId('done-sketching').click()
  await expect(page.getByRole('tab', { name: /Stressors/ })).toHaveAttribute('aria-selected', 'true')
  await expect(element(page, SERVICE_ALIAS)).toBeAttached()
})

test('a stressor is written, grouped under a new end state, ticked on the canvas and taken back', async ({ page, request }) => {
  const id = await analysisOf(request, 'Stress analysis — stressor round trip')
  await workspace(page, id, 'stressors')
  const text = page.getByTestId('stressor-input').first()
  await text.fill('Forty engagement repositories promote in the same week')
  await text.press('Enter')
  const row = page.locator('tr.st-row[data-row="S1"]')
  await expect(row).toContainText('Forty engagement repositories')

  await row.getByTestId('end-state-pick').click()
  const chooser = page.getByLabel('End state', { exact: true })
  await chooser.fill('Promotions stall')
  await chooser.press('Enter')
  await expect(row.getByTestId('end-state-pick')).toHaveText('Promotions stall')

  await element(page, SERVICE_ALIAS).click({ force: true })
  const grid = page.getByTestId('incidence-grid')
  await expect(grid).toContainText('Repository Promotion Service')
  await expect(page.locator('[data-marked]')).toHaveCount(1)

  await row.locator('.rm-row').click()
  await expect(page.locator('tr.st-row')).toHaveCount(0)
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(page.locator('tr.st-row')).toHaveCount(1)
  await expect(page.locator('tr.st-row').first()).toContainText('Forty engagement repositories')
})

test('focusing an end state turns the grid and marks what its stressors hit', async ({ page, request }) => {
  const id = await analysisOf(request, 'Stress analysis — focus')
  const naive = await (await request.get(`/api/documents/${encodeURIComponent(id)}`)).json() as { extra: Record<string, string> }
  const scope = await (await request.get(`/api/change-sets/${encodeURIComponent(naive.extra['naive-candidate'])}`)).json() as
    { record: { scope: string[] } }
  const [service, artifacts] = ['SRV@', 'PRC@'].map((prefix) => scope.record.scope.find((ref) => ref.startsWith(prefix)) ?? '')
  const edit = (table: string, rows: unknown[]) => request.patch(
    `/api/documents/${encodeURIComponent(id)}/tables/${table}`, { data: { rows, dry_run: false } })
  await edit('end-states', [{ op: 'add', cells: { end_state: 'Promotions stall' } }])
  await edit('stressors', [
    { op: 'add', cells: { stressor: 'Forty promote at once', set: 'design', end_state: 'E1' } },
    { op: 'add', cells: { stressor: 'The board is dissolved', set: 'design', end_state: 'E1' } },
  ])
  await edit('incidence', [
    { op: 'add', cells: { stressor: 'S1', component: service } },
    { op: 'add', cells: { stressor: 'S1', component: artifacts } },
    { op: 'add', cells: { stressor: 'S2', component: artifacts } },
  ])

  await workspace(page, id, 'end-states')
  await page.locator('.es[data-end-state="E1"]').getByRole('button', { name: '◎ Focus' }).click()
  const grid = page.getByTestId('incidence-grid')
  await expect(grid).toContainText('“Promotions stall” in focus')
  await expect(grid.locator('th.col')).toHaveCount(2)
  await expect(page.locator(`[data-marked]`)).toHaveCount(2)
  await expect(page.getByTestId('workspace-canvas').locator('.ws-mark-tag', { hasText: 'hit by 2 of 2' })).toBeAttached()
  expect(await element(page, ARTIFACTS_ALIAS).count()).toBe(1)

  await grid.getByRole('button', { name: 'Leave focus' }).click()
  await expect(page.getByTestId('incidence-grid')).toHaveCount(0)
  await expect(page.locator('[data-marked]')).toHaveCount(0)
})

test('a rename on the sketching canvas is saved to the candidate, and renaming it back takes it away', async ({ page, request }) => {
  const id = await analysisOf(request, 'Stress analysis — sketching')
  await workspace(page, id, 'naive')
  await page.getByTestId('sketch').click()
  const service = page.getByTestId('candidate-canvas').locator(`g.lab-element[data-alias="${SERVICE_ALIAS}"] .lab-grip`)
  const rename = async (name: string) => {
    await service.click({ button: 'right', force: true })
    await page.getByRole('dialog', { name: 'element' }).getByRole('menuitem', { name: 'Rename' }).click()
    await page.getByRole('dialog', { name: 'rename' }).getByLabel('Name').fill(name)
    await page.getByRole('button', { name: 'Keep rename' }).click()
  }
  const operations = page.getByTestId('candidate-operations').locator('tr.oprow')

  await rename('Promotion Review Service')
  await expect(page.getByTestId('saved-at')).toContainText('Saved to the candidate')
  await expect(operations).toHaveCount(1)
  await expect(operations.first()).toContainText('Promotion Review Service')

  await rename('Repository Promotion Service')
  await expect(operations).toHaveCount(0)
  await page.getByTestId('done-sketching').click()
  await expect(page.getByTestId('workspace-canvas')).toBeVisible()
})

test('a third of the design stressors is held out and judged on the naive', async ({ page, request }) => {
  const id = await analysisOf(request, 'Stress analysis — test set')
  const written = await request.patch(`/api/documents/${encodeURIComponent(id)}/tables/stressors`, {
    data: {
      dry_run: false,
      rows: ['Demand doubles', 'A regulator bans the service', 'The founder leaves']
        .map((stressor) => ({ op: 'add', cells: { stressor, set: 'design' } })),
    },
  })
  expect(written.ok(), await written.text()).toBe(true)
  await workspace(page, id, 'stressors')
  await expect(page.locator('tr.st-row')).toHaveCount(3)

  await page.getByTestId('add-test-set').click()
  await page.getByTestId('hold-out').click()
  // Asked in the section itself, Cancel focused: a stray Enter holds nothing out.
  await expect(page.getByTestId('hold-out-ask')).toContainText('Move 1 of the 3 design stressors')
  await page.getByTestId('hold-out-confirm').click()
  await expect(page.locator('tr.st-row')).toHaveCount(2)
  const section = page.getByTestId('test-set')
  await expect(section).toContainText('1 stressor held apart')

  await section.locator('[data-judge="naive"]').click()
  const walk = page.getByTestId('judge-walk')
  await walk.getByRole('button', { name: 'Fails' }).click()
  await expect(walk.locator('tr.jr').first()).toContainText('fails')
  await expect(section.getByTestId('residuality').first()).toContainText('survives 0 of 1')
})
