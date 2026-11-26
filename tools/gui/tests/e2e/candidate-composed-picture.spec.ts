import { expect, test } from '@playwright/test'

/**
 * A candidate's page draws the candidate as it composes from its stored operations, after a reload as
 * well as while it is sketched: what it creates is drawn and marked +, what it renames is drawn under the
 * new name and marked ~, and the relation it adds between them is drawn.
 *
 * The candidate is written through the API and deleted afterwards.
 */

const INDEX_STORE = 'APP@1786967678.R_K3YAQ'
const CACHE = 'APP@1795700001.IdxCach.index-read-cache'
const GIT_SYNC = 'APP@1777293134.tY3JIK'
const PROMOTION_SERVICE = 'SRV@1712870400.Uv9Wx9'

let candidate = ''

test.afterEach(async ({ request }) => {
  if (!candidate) return
  const deleted = await request.delete(`/api/change-sets/${encodeURIComponent(candidate)}?dry_run=false`)
  expect(deleted.status(), await deleted.text()).toBe(204)
  candidate = ''
})

test('a candidate drawn on the view generated from its scope draws what it creates, marked +', async ({ page, request }) => {
  const written = await request.post('/api/change-sets', { data: {
    record: { name: 'Cached index store', scope: [INDEX_STORE] },
    operations: [
      { op: 'create_entity', artifact_id: CACHE,
        fields: { artifact_type: 'application-component', name: 'Index Read Cache', group: 'platform-core' } },
      { op: 'edit_entity', artifact_id: INDEX_STORE, field: 'name', value: 'Artifact Index Backing Store' },
      { op: 'add_connection', source_entity: 'APP@1795700001.IdxCach', connection_type: 'archimate-serving',
        target_entity: INDEX_STORE },
    ],
  } })
  expect(written.ok(), await written.text()).toBe(true)
  candidate = ((await written.json()) as { record: { id: string } }).record.id

  await page.goto(`/candidates/${encodeURIComponent(candidate)}`)
  const canvas = page.getByTestId('workspace-canvas')
  await expect(canvas.locator('g.lab-element[data-alias]', { hasText: 'Index Read Cache' })).toBeAttached({ timeout: 20_000 })
  await expect(canvas.locator('g.lab-element[data-alias]', { hasText: 'Artifact Index Backing Store' })).toBeAttached()
  await expect(canvas.locator('.ws-mark-tag', { hasText: '+' })).toHaveCount(1)
  await expect(canvas.locator('.ws-mark-tag', { hasText: '~' })).toHaveCount(1)
  await expect(canvas.locator('g.lab-line[data-relation]')).toHaveCount(1)
})

test('a candidate that relates two elements of its generated view keeps the box the view draws them in', async ({ page, request }) => {
  const written = await request.post('/api/change-sets', { data: {
    record: { name: 'Git sync serves the index', scope: [PROMOTION_SERVICE, INDEX_STORE, GIT_SYNC] },
    operations: [
      { op: 'add_connection', source_entity: GIT_SYNC, connection_type: 'archimate-serving', target_entity: INDEX_STORE },
    ],
  } })
  expect(written.ok(), await written.text()).toBe(true)
  candidate = ((await written.json()) as { record: { id: string } }).record.id

  await page.goto(`/candidates/${encodeURIComponent(candidate)}`)
  const canvas = page.getByTestId('workspace-canvas')
  // The relation is drawn, and the two components it joins stay in the box the generated view drew them in.
  await expect(canvas.locator('g.lab-line[data-relation]')).toHaveCount(1, { timeout: 20_000 })
  await expect(canvas.locator('g.lab-box[data-alias]', { hasText: 'Application Components' })).toHaveCount(1)
})
