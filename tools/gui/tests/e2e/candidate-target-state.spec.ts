import { expect, test } from '@playwright/test'

/**
 * *Apply as a target state…*, *Move into the baseline…* and *Withdraw…* on a candidate's page.
 *
 * The dry runs are the server's own. The writes are answered here, at the network, and the candidate's
 * record with them: a real target state writes plateaus and copies into the model of whatever repository
 * the suite is served from. What is held here is the GUI's half: each confirmation asks for the write
 * (`dry_run: false`), the page then reads where the target state stands, shows the band, stops offering a
 * direct apply, and offers the move.
 */

const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const SERVICE = 'SRV@1712870400.Uv9Wx9'
const STANDING = {
  baseline: 'PLT@1795600000.aaaaaa.baseline-target-spec', target: 'PLT@1795600000.bbbbbb.target-target-spec',
  gap: 'ASS@1795600000.cccccc.gap-target-spec', copies: { [SERVICE]: 'SRV@1795600000.dddddd.copy' }, added: {},
}

let candidate = ''

test.beforeEach(async ({ request }) => {
  const created = await request.post('/api/candidates', {
    data: {
      record: { name: 'Target state spec candidate', diagram: DIAGRAM },
      operations: [{ op: 'edit_entity', artifact_id: SERVICE, field: 'name', value: 'Promotion Review Service' }],
    },
  })
  expect(created.ok(), await created.text()).toBe(true)
  candidate = ((await created.json()) as { record: { id: string } }).record.id
})

test.afterEach(async ({ request }) => {
  if (candidate) await request.delete(`/api/candidates/${encodeURIComponent(candidate)}?dry_run=false`)
  candidate = ''
})

test('a target state is applied after its dry run, and then offers the move into the baseline', async ({ page }) => {
  const asked: string[] = []
  let standing = false
  await page.route('**/api/candidates/*/apply-as-target-state', async (route) => {
    const body = route.request().postDataJSON() as { dry_run: boolean }
    asked.push(`apply ${body.dry_run}`)
    if (body.dry_run) return route.continue()
    standing = true
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ candidate, dry_run: false, applied: true, standing: [], target_state: STANDING }),
    })
  })
  await page.route('**/api/candidates/*/move-into-baseline', async (route) => {
    const body = route.request().postDataJSON() as { dry_run: boolean }
    asked.push(`move ${body.dry_run}`)
    // The candidate's edit, stored against a revision, and what the model holds where it writes.
    const edit = { op: 'edit_entity', artifact_id: SERVICE, field: 'name', value: 'Promotion Review Service',
      base: { revision: 'r1' } }
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        candidate, dry_run: body.dry_run, integrated: false, operations: [edit],
        standing: [{ operation: edit, standing: 'applies', reason: 'applies', holds: 'Review Service' }],
      }),
    })
  })
  // The candidate's record as the server holds it once the target state is written.
  await page.route(/\/api\/candidates\/[^/?]+$/, async (route) => {
    if (route.request().method() !== 'GET' || !standing) return route.continue()
    const response = await route.fetch()
    const read = await response.json() as { record: Record<string, unknown>; version: string }
    return route.fulfill({ response, json: { ...read, record: { ...read.record, 'target-state': STANDING } } })
  })
  await page.goto(`/candidates/${encodeURIComponent(candidate)}`)
  await page.getByRole('button', { name: 'Apply as a target state…' }).click()

  const confirmation = page.getByTestId('target-state-confirm')
  await expect(confirmation).toContainText('beside the baseline in one write')
  await expect(confirmation).toContainText('1 "(target)" copy of what it changes')
  await page.getByTestId('target-state-confirm-write').click()

  const band = page.getByTestId('target-state')
  await expect(band).toContainText('In the model as a target state')
  await expect(page.getByRole('button', { name: 'Apply to the model…' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Move into the baseline…' }).click()
  await expect(confirmation).toContainText('Move Target state spec candidate into the baseline')
  // An edit stored against a revision is read against what the model holds, as the apply card reads it.
  await confirmation.locator('summary').click()
  await expect(confirmation.getByTestId('field-change').locator('ins')).toHaveText(/Promotion/)
  expect(asked).toEqual(['apply true', 'apply false', 'move true'])
})

test('a target state is withdrawn after its dry run, and the candidate can then be abandoned', async ({ page }) => {
  const asked: string[] = []
  let standing = true
  await page.route('**/api/candidates/*/withdraw-target-state', async (route) => {
    const body = route.request().postDataJSON() as { dry_run: boolean }
    asked.push(`withdraw ${body.dry_run}`)
    if (!body.dry_run) standing = false
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ candidate, dry_run: body.dry_run, released: !body.dry_run, operations: [] }),
    })
  })
  await page.route(/\/api\/candidates\/[^/?]+$/, async (route) => {
    if (route.request().method() !== 'GET' || !standing) return route.continue()
    const response = await route.fetch()
    const read = await response.json() as { record: Record<string, unknown>; version: string }
    return route.fulfill({ response, json: { ...read, record: { ...read.record, 'target-state': STANDING } } })
  })
  await page.goto(`/candidates/${encodeURIComponent(candidate)}`)
  await page.getByTestId('abandon-candidate').click()
  await expect(page.getByTestId('abandon-card')).toContainText('Withdraw it first')
  await page.getByTestId('abandon-withdraw').click()

  const confirmation = page.getByTestId('target-state-confirm')
  await expect(confirmation).toContainText('Withdraw the target state of Target state spec candidate')
  await expect(confirmation).toContainText('The baseline stays as it is')
  await page.getByTestId('target-state-confirm-write').click()
  await expect(page.getByTestId('target-state')).toHaveCount(0)

  await page.getByTestId('abandon-candidate').click()
  await expect(page.getByTestId('abandon-reject')).toBeVisible()
  await expect(page.getByTestId('abandon-delete')).toBeVisible()
  expect(asked).toEqual(['withdraw true', 'withdraw false'])
})
