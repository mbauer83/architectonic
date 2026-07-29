import { test, expect } from './coverage-fixture'

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
    localStorage.setItem('arch_group_diagram-collection', 'uncategorized')
    localStorage.setItem('arch_group_document-collection', 'uncategorized')
  })
})

const createdSlugs: string[] = []
const uniqueSlug = () => {
  const slug = `trace-authoring-e2e-${Date.now()}`
  createdSlugs.push(slug)
  return slug
}

test.afterEach(async ({ request }) => {
  for (const slug of createdSlugs.splice(0)) {
    await request.post('/api/viewpoints/remove', { data: { slug, dry_run: false } })
  }
})

test('default controls, deep pattern editing, validation, preview, and round-trip', async ({ page, request }) => {
  await page.goto('/entities?viewpoint=motivation-coverage')
  const toolbar = page.getByRole('form', { name: 'Viewpoint parameters' })
  await expect(toolbar).toBeVisible({ timeout: 15000 })
  await expect(toolbar.getByRole('checkbox', { name: 'goal', exact: true })).toBeVisible()
  await expect(toolbar.getByRole('checkbox', { name: 'outcome', exact: true })).toBeVisible()
  await expect(toolbar.getByRole('checkbox', { name: 'requirement', exact: true })).toBeVisible()
  await expect(toolbar.getByRole('checkbox', { name: 'gaps_only', exact: true })).toBeVisible()

  const slug = uniqueSlug()
  await page.goto('/viewpoints')
  await page.getByRole('button', { name: '+ Create viewpoint' }).click()
  await page.getByRole('textbox', { name: 'slug' }).fill(slug)
  await page.getByRole('textbox', { name: 'name' }).fill('Trace Authoring Acceptance')
  await page.getByRole('button', { name: 'Query' }).click()

  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Coverage trace patterns' }) })
  await expect(panel.getByText('No trace patterns.')).toBeVisible()
  await panel.getByRole('button', { name: '+ Add trace pattern' }).click()
  const pattern = panel.locator('.pattern').filter({ has: page.getByPlaceholder('pattern name') })

  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.locator('.issue-list li.error')).toBeVisible()
  await expect(pattern).toHaveClass(/highlighted/)

  await pattern.getByPlaceholder('pattern name').fill('authored_coverage')
  await pattern.getByRole('checkbox', { name: 'goal', exact: true }).check()
  await pattern.getByRole('button', { name: '+ Add branch edge' }).click()
  const branch = pattern.locator('.edge-row').filter({ has: page.getByPlaceholder('edge label') })
  await branch.getByPlaceholder('edge label').fill('goal_to_outcome')
  await branch.locator('select').nth(0).selectOption('archimate-realization')
  await branch.locator('select').nth(1).selectOption('incoming')
  await branch.locator('select').nth(2).selectOption('outcome')

  await pattern.getByRole('button', { name: '+ Add branch edge' }).click()
  const requirementBranch = pattern.locator('.edge-row')
    .filter({ has: page.getByPlaceholder('edge label') })
    .filter({ hasNot: page.locator('input[placeholder="edge label"][value="goal_to_outcome"]') })
  await requirementBranch.getByPlaceholder('edge label').fill('outcome_to_requirement')
  await requirementBranch.locator('select').nth(0).selectOption('archimate-realization')
  await requirementBranch.locator('select').nth(1).selectOption('incoming')
  await requirementBranch.locator('select').nth(2).selectOption('requirement')

  await pattern.getByRole('button', { name: '+ Add shortcut edge' }).click()
  const shortcut = pattern.locator('.edge-row').filter({ hasText: 'shortcut' })
  await shortcut.locator('select').nth(0).selectOption('archimate-influence')
  await shortcut.locator('select').nth(1).selectOption('incoming')
  await shortcut.locator('select').nth(2).selectOption('requirement')
  await shortcut.locator('select').nth(3).selectOption('shortcut')

  const leaf = pattern.locator('.sub').filter({ hasText: 'leaf' })
  await leaf.locator('select').nth(0).selectOption('derived-reachability')
  await leaf.locator('select').nth(1).selectOption('archimate-realization')
  await leaf.locator('select').nth(2).selectOption('registry')
  await leaf.locator('select').nth(3).selectOption('permitted-realizers-of-requirement')

  await panel.getByRole('button', { name: 'Preview cells' }).click()
  const preview = panel.locator('.vp-trace-table')
  await expect(preview.getByText('incomplete branch 2/3')).toBeVisible()
  await expect(preview.getByText('none observed')).toBeVisible()
  await expect(preview.getByText('observation')).toBeVisible()

  await page.getByRole('button', { name: 'Test run' }).click()
  await expect(page.locator('.test-run-counts')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.issue-list li.error')).toHaveCount(0)
  const persisted = page.waitForResponse((response) => {
    if (!response.url().endsWith('/api/viewpoints') || response.request().method() !== 'POST') return false
    const body = response.request().postDataJSON() as { dry_run?: boolean }
    return body.dry_run === false
  })
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  const persistBody = await (await persisted).json() as { ok: boolean }
  expect(persistBody.ok, JSON.stringify(persistBody)).toBe(true)
  await expect(page.locator('tr', { hasText: slug })).toBeVisible()

  const response = await request.get('/api/viewpoints')
  const body = await response.json() as { viewpoints: Array<Record<string, unknown>> }
  const saved = body.viewpoints.find((definition) => definition.slug === slug)
  expect(saved).toMatchObject({
    query: {
      trace_patterns: [{
        name: 'authored_coverage', applies_to: ['goal'],
        branches: {
          goal_to_outcome: { connection: 'archimate-realization', direction: 'incoming', endpoint: { type: 'outcome' } },
          outcome_to_requirement: { connection: 'archimate-realization', direction: 'incoming', endpoint: { type: 'requirement' } },
        },
        shortcuts: [{ connection: 'archimate-influence', direction: 'incoming', endpoint: { type: 'requirement' }, status: 'shortcut' }],
        leaf: {
          kind: 'derived-reachability', connection: 'archimate-realization',
          endpoint: { registry: 'permitted-realizers-of-requirement' },
        },
      }],
    },
  })
})
