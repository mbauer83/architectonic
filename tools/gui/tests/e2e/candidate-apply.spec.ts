import { expect, test } from '@playwright/test'

/**
 * *Apply to the model…* on a candidate's page: the dry run first, read as what would be written, then
 * the confirmation, which asks the server to apply for real and closes once the candidate is integrated.
 *
 * The dry run is the server's own. The apply itself is answered here, at the network: a real apply
 * writes to the model of whatever repository the suite is served from, and an integrated candidate is
 * kept as the record of what was written, so nothing could take it back. What is held here is the GUI's
 * half: that the confirmation asks for the write (`dry_run: false`) and reads the server's answer.
 */

const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
const SERVICE = 'SRV@1712870400.Uv9Wx9'

let candidate = ''

test.beforeEach(async ({ request }) => {
  const created = await request.post('/api/change-sets', {
    data: {
      record: { name: 'Apply spec candidate', diagram: DIAGRAM },
      operations: [{ op: 'edit_entity', artifact_id: SERVICE, field: 'name', value: 'Promotion Review Service' }],
    },
  })
  expect(created.ok(), await created.text()).toBe(true)
  candidate = ((await created.json()) as { record: { id: string } }).record.id
})

test.afterEach(async ({ request }) => {
  if (candidate) await request.delete(`/api/change-sets/${encodeURIComponent(candidate)}?dry_run=false`)
  candidate = ''
})

test('the apply is confirmed after its dry run, and the confirmation asks for the write', async ({ page }) => {
  const asked: unknown[] = []
  await page.route('**/api/change-sets/*/apply', async (route) => {
    const body = route.request().postDataJSON() as { dry_run: boolean }
    asked.push(body.dry_run)
    if (body.dry_run) return route.continue()
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ candidate, dry_run: false, integrated: true, standing: [] }),
    })
  })
  await page.goto(`/candidates/${encodeURIComponent(candidate)}`)
  await page.getByRole('button', { name: 'Apply to the model…' }).click()

  const confirmation = page.getByTestId('apply-candidate')
  await expect(confirmation).toContainText('Writes 1 operation to the model in one write.')
  await expect(confirmation).toContainText(`Set name of ${SERVICE}`)
  await page.getByTestId('apply-confirm').click()

  await expect(confirmation).toBeHidden()
  await expect(page.getByText('it is integrated.')).toBeVisible()
  expect(asked).toEqual([true, false])
})
