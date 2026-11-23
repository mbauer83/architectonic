import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

/**
 * The stress-analysis workspace, driven as an analyst drives it: starting an analysis from a diagram,
 * a stressor written, grouped and ticked on the canvas, and an end state in focus.
 *
 * Each test makes its own analysis and deletes its document afterwards. A candidate architecture has
 * no delete route yet, so the naive architecture each test starts stays behind as a draft.
 */

const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const SERVICE_ALIAS = 'SRV_Uv9Wx9'
const ARTIFACTS_ALIAS = 'PRC_0Rz5Ex'

const created: string[] = []

/** Whether the served engagement declares the stress-analysis document type (shipped as a default). */
const declaresStressAnalysis = async (request: APIRequestContext): Promise<boolean> => {
  const types = await (await request.get('/api/document-types')).json() as { document_types: { doc_type: string }[] }
  return types.document_types.some((one) => one.doc_type === 'stress-analysis')
}

/** An analysis of the diagram, made through the same two writes the start page makes. */
const analysisOf = async (request: APIRequestContext, title: string): Promise<string> => {
  const naive = await request.post('/api/change-sets', { data: { record: { name: 'Naive architecture' }, diagram: DIAGRAM } })
  expect(naive.ok(), await naive.text()).toBe(true)
  const naiveId = (await naive.json() as { record: { id: string } }).record.id
  const document = await request.post('/api/documents', {
    data: {
      doc_type: 'stress-analysis', title, dry_run: false,
      extra_frontmatter: { 'naive-candidate': naiveId, 'scope-diagram': DIAGRAM },
    },
  })
  expect(document.ok(), await document.text()).toBe(true)
  const id = (await document.json() as { artifact_id: string }).artifact_id
  created.push(id)
  return id
}

const workspace = (page: Page, id: string, tab: string) =>
  page.goto(`/documents/${encodeURIComponent(id)}/workspace?tab=${tab}`)

const element = (page: Page, alias: string) =>
  page.getByTestId('workspace-canvas').locator(`g.lab-element[data-alias="${alias}"] .lab-grip`)

test.beforeEach(async ({ request }) => {
  test.skip(!(await declaresStressAnalysis(request)), 'the served engagement does not declare the stress-analysis document type')
})

test.afterEach(async ({ request }) => {
  for (const id of created.splice(0)) await request.delete(`/api/documents/${encodeURIComponent(id)}?dry_run=false`)
})

test('starting an analysis from a diagram opens the naive architecture in the workspace', async ({ page }) => {
  await page.goto('/stress-analyses/new')
  await page.getByTestId('analysis-name').fill('Stress analysis — start flow')
  await page.getByTestId('scope-diagram').selectOption(DIAGRAM)
  await expect(page.getByTestId('scope-count')).not.toContainText(/^0 elements/)
  await expect(element(page, SERVICE_ALIAS)).toBeAttached()
  await page.getByTestId('start-naive').click()

  await page.waitForURL(/\/workspace\?tab=naive$/)
  created.push(decodeURIComponent(page.url().split('/documents/')[1].split('/workspace')[0]))
  await expect(page.getByRole('tab', { name: /Naive architecture/ })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('candidate-operations')).toContainText('naive architecture · the initial candidate')
  await expect(element(page, SERVICE_ALIAS)).toBeAttached()
})

test('a stressor is written, grouped under a new end state, ticked on the canvas and taken back', async ({ page, request }) => {
  const id = await analysisOf(request, 'Stress analysis — stressor round trip')
  await workspace(page, id, 'stressors')
  await page.getByTestId('add-stressor').click()
  const text = page.getByLabel('Stressor', { exact: true })
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
    await page.getByRole('dialog', { name: 'element' }).getByRole('button', { name: 'Rename' }).click()
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
