/**
 * Two sessions editing one diagram: the first save is written, and the second — made from what its session
 * read before the first — is refused rather than written over it, with the reason and a Reload that reads the
 * diagram as it is now. The canvas sends the revision it read with every save (`base_revision`).
 *
 * On a diagram of its own, made and removed here, so the self-model's diagrams are not changed.
 */
import { expect, test, type Browser, type Page } from '@playwright/test'

const MEMBERS = ['PRC@1712870400.0Rz5Ex.promote-artifacts', 'SRV@1712870400.Uv9Wx9.repository-promotion-service']
let diagram = ''

test.beforeAll(async ({ request }) => {
  const made = await request.post('/api/diagrams', { data: {
    diagram_type: 'archimate-layered', name: 'Concurrent saves', entity_ids: MEMBERS, connection_ids: [],
    dry_run: false,
  } })
  expect(made.ok(), await made.text()).toBe(true)
  diagram = (await made.json()).artifact_id
})

test.afterAll(async ({ request }) => {
  if (diagram) await request.delete(`/api/diagrams/${encodeURIComponent(diagram)}?dry_run=false`)
})

const session = async (browser: Browser): Promise<Page> => {
  const page = await (await browser.newContext()).newPage()
  await page.goto(`/diagrams/${encodeURIComponent(diagram)}`)
  await page.getByTestId('diagram-edit').click()
  await expect(page.getByTestId('layout-lab-canvas').locator('g.lab-element').first()).toBeVisible()
  return page
}

/** Add the first element the panel offers, and save what that changes. */
const addAndSave = async (page: Page, nth: number) => {
  const member = page.getByRole('region', { name: 'Add from model' }).locator('button[draggable=true]').nth(nth)
  const preview = page.waitForResponse(response => response.url().endsWith('/layout/geometry/preview'))
  await member.focus()
  await member.press('Enter')
  expect((await preview).ok()).toBe(true)
  await page.getByTestId('edit-save').click()
  const confirm = page.getByRole('button', { name: 'Confirm and save' })
  if (await confirm.isVisible()) await confirm.click()
}

test('the second of two sessions saving one diagram is refused and offered a reload', async ({ browser }) => {
  const first = await session(browser)
  const second = await session(browser)

  const written = first.waitForResponse(response => response.request().method() === 'PUT')
  await addAndSave(first, 0)
  expect((await written).status()).toBe(200)

  const refused = second.waitForResponse(response => response.request().method() === 'PUT')
  await addAndSave(second, 1)
  expect((await refused).status()).toBe(409)
  const bar = second.getByTestId('diagram-edit-bar')
  await expect(bar.getByRole('alert')).toContainText('changed since it was read')
  await bar.getByTestId('edit-reload').click()
  await expect(bar.getByTestId('edit-reload')).toHaveCount(0)
  await expect(second.getByTestId('change-count')).toHaveText('No changes')
})
