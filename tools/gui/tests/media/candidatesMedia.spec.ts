import { expect, test } from '@playwright/test'
import { capture, scrollToStable, watch, type CaptureProvenance } from './mediaHelpers'
import {
  AnalysisFixture, ADAPTATION_NAME, DIAGRAM, INDEX_STORE, NAIVE_NAME, PROMOTION_SERVICE, promotionPipelineAnalysis,
} from './analysisFixture'

/**
 * The documentation's pictures of candidate architectures and stress analyses.
 *
 * Each figure's candidates and analysis are written through the API in the test and deleted after it
 * (see `analysisFixture.ts`), so the repository is as it was before the run. The data is the guides'
 * worked example rather than anything the self-model holds, and the manifest says so.
 */

const provenance = (testName: string, artifactIds: readonly string[] = []): CaptureProvenance => ({
  test_name: testName,
  artifact_ids: artifactIds,
  synthetic_augmentation: true,
})

let fixture: AnalysisFixture

test.beforeEach(({ request }) => { fixture = new AnalysisFixture(request) })
test.afterEach(async () => { await fixture.removeAll() })

test('a candidate architecture and its operations', async ({ page }) => {
  const problems = watch(page)
  const candidate = await fixture.candidate({ name: 'Cached index store', scope: [INDEX_STORE] }, [
    { op: 'create_entity', artifact_id: 'APP@1795700000.IdxCach.index-read-cache',
      fields: { artifact_type: 'application-component', name: 'Index Read Cache', group: 'platform-core' } },
    { op: 'edit_entity', artifact_id: INDEX_STORE, field: 'name', value: 'Artifact Index Backing Store' },
    { op: 'add_connection', source_entity: 'APP@1795700000.IdxCach', connection_type: 'archimate-serving',
      target_entity: INDEX_STORE },
  ])
  await page.goto(`/candidates/${encodeURIComponent(candidate)}`, { waitUntil: 'load' })
  await expect(page.getByTestId('candidate-operations').locator('tr.oprow')).toHaveCount(3, { timeout: 20_000 })
  await expect(page.locator('.svg-wrap svg, [data-testid="candidate-canvas"]').first()).toBeVisible({ timeout: 20_000 })
  // The figure's subject is the candidate drawn as it composes, which arrives after the picture it is drawn
  // over: what it creates, the rename and the relation, with nothing still loading.
  const canvas = page.getByTestId('workspace-canvas')
  await expect(canvas.locator('g.lab-element[data-alias]', { hasText: 'Index Read Cache' })).toBeAttached({ timeout: 20_000 })
  await expect(canvas.locator('g.lab-element[data-alias]', { hasText: 'Artifact Index Backing Store' })).toBeAttached()
  await expect(canvas.locator('g.lab-line[data-relation]')).toHaveCount(1)
  await expect(canvas.getByTestId('canvas-composing')).toHaveCount(0)
  await capture(page, 'candidate-page.png', provenance('a candidate architecture and its operations', [INDEX_STORE]))
  expect(problems, 'runtime problems while capturing candidate-page.png').toEqual([])
})

test('two candidates integrated, one conflict open', async ({ page }) => {
  const problems = watch(page)
  const queued = await fixture.candidate({ name: 'Queued promotion', scope: [PROMOTION_SERVICE], diagram: DIAGRAM }, [
    { op: 'edit_entity', artifact_id: PROMOTION_SERVICE, field: 'name', value: 'Queued Promotion Service' },
  ])
  const batched = await fixture.candidate({ name: 'Batched promotion', scope: [PROMOTION_SERVICE], diagram: DIAGRAM }, [
    { op: 'edit_entity', artifact_id: PROMOTION_SERVICE, field: 'name', value: 'Batched Promotion Service' },
  ])
  const query = new URLSearchParams([['candidate', queued], ['candidate', batched], ['diagram', DIAGRAM]])
  await page.goto(`/candidates/compare?${query.toString()}`, { waitUntil: 'load' })
  await page.getByTestId('integrate-compared').click()
  await expect(page.getByTestId('integrate-card')).toBeVisible()
  await expect(page.getByTestId('integration-conflict').first()).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('No diagram to draw', { exact: false })).toHaveCount(0, { timeout: 20_000 })
  await capture(page, 'candidate-integrate.png',
    provenance('two candidates integrated, one conflict open', [PROMOTION_SERVICE, DIAGRAM]))
  expect(problems, 'runtime problems while capturing candidate-integrate.png').toEqual([])
})

test('the start page of a stress analysis', async ({ page }) => {
  // Filled in and not submitted: the page is the subject, and starting would write an analysis.
  const problems = watch(page)
  await page.goto('/stress-analyses/new', { waitUntil: 'load' })
  await page.getByTestId('analysis-name').fill('Stress analysis — promotion pipeline')
  await page.getByTestId('analysis-context').fill(
    'Engagements multiply over the next two years; the analysis informs whether promotion needs a queue.')
  await page.getByTestId('naive-name').fill(NAIVE_NAME)
  await capture(page, 'stress-start.png', provenance('the start page of a stress analysis'))
  expect(problems, 'runtime problems while capturing stress-start.png').toEqual([])
})

test('the naive architecture sketched on its canvas', async ({ page }) => {
  const problems = watch(page)
  // The three model elements are placed through the API; the Promotion Queue is created on the canvas,
  // as the guide does it, so the picture shows it as the sketch session draws a created element.
  const { document } = await promotionPipelineAnalysis(fixture, { queue: false })
  await page.goto(`/documents/${encodeURIComponent(document)}/workspace?tab=naive&sketch=naive`, { waitUntil: 'load' })
  const sketch = page.getByTestId('candidate-canvas')
  await expect(sketch.locator('g.lab-element').first()).toBeVisible({ timeout: 20_000 })
  const understood = page.getByRole('button', { name: 'Understood' })
  if (await understood.count()) await understood.click()
  const paper = sketch.getByTestId('layout-lab-canvas')
  const area = (await paper.boundingBox())!
  await paper.click({ button: 'right', position: { x: 30, y: area.height - 40 } })
  const create = page.getByRole('dialog', { name: 'create' })
  await create.getByLabel('Filter element types').fill('application component')
  await create.locator('[role="option"][data-type="application-component"]').click()
  await create.getByLabel('Name', { exact: true }).fill('Promotion Queue')
  await create.getByRole('button', { name: 'Create draft' }).click()
  await expect(create).toHaveCount(0)
  await expect(sketch.locator('g.lab-element').filter({ hasText: 'Promotion Queue' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('candidate-operations').locator('tr.oprow')).toHaveCount(1, { timeout: 20_000 })
  await capture(page, 'stress-naive-canvas.png', provenance('the naive architecture sketched on its canvas', [document]))
  expect(problems, 'runtime problems while capturing stress-naive-canvas.png').toEqual([])
})

test('stressors and the incidence of one of them', async ({ page }) => {
  const problems = watch(page)
  const { document } = await promotionPipelineAnalysis(fixture)
  await page.goto(`/documents/${encodeURIComponent(document)}/workspace?tab=stressors`, { waitUntil: 'load' })
  const row = page.locator('tr.st-row[data-row="S1"]')
  await expect(row).toBeVisible({ timeout: 20_000 })
  await row.locator('td').first().click()
  await expect(page.getByTestId('incidence-grid')).toBeVisible()
  await expect(page.getByTestId('workspace-canvas')).toBeVisible()
  // The canvas stays beside the tab as it scrolls: the input and its Perspectives line at the top, the
  // incidence grid of the stressor in focus below the table.
  await scrollToStable(page, '[data-testid="stressor-input"]', 90)
  await capture(page, 'stress-workspace.png', provenance('stressors and the incidence of one of them', [document]))
  expect(problems, 'runtime problems while capturing stress-workspace.png').toEqual([])
})

test('the test set judged on the naive and on an adaptation', async ({ page }) => {
  const problems = watch(page)
  const { document, adaptation } = await promotionPipelineAnalysis(fixture)
  await page.goto(`/documents/${encodeURIComponent(document)}/workspace?tab=stressors`, { waitUntil: 'load' })
  const section = page.getByTestId('test-set')
  await expect(section).toContainText('3 stressors held apart', { timeout: 20_000 })
  await expect(section).toContainText(ADAPTATION_NAME)
  await section.locator('button.head').click()
  await section.locator(`[data-judge="${adaptation}"]`).click()
  await expect(page.getByTestId('judge-walk')).toBeVisible()
  await scrollToStable(page, '[data-testid="test-set"]', 100)
  await capture(page, 'stress-test-set.png', provenance('the test set judged on the naive and on an adaptation', [document]))
  expect(problems, 'runtime problems while capturing stress-test-set.png').toEqual([])
})
