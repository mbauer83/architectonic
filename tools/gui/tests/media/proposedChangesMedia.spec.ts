import { expect, test } from '@playwright/test'
import { capture, watch, type CaptureProvenance } from './mediaHelpers'

/**
 * The documentation's picture of what an engagement is holding against promoted content.
 *
 * The list is rendered from `/api/changes`, and that answer is supplied here rather than produced
 * by editing this repository's own promoted artifacts. A change is a real write: recording two to
 * be photographed would leave them in the self-model, and discarding them afterwards would leave
 * the terminal records the lifecycle keeps on purpose.
 *
 * So the page is real, the data is representative, and the manifest says so —
 * `synthetic_augmentation: true`, the same declaration the scratchpad and security captures carry.
 *
 * The subject is what the page exists to answer: which artifacts you have changed, what each
 * change would make them say beside what they say now, and which of them needs something doing
 * about it. One of each, because a page showing only the settled case argues nothing.
 */

const PROVENANCE: CaptureProvenance = {
  test_name: 'local changes against promoted content',
  artifact_ids: [],
  synthetic_augmentation: true,
}

const CHANGES = [
  {
    artifact_id: 'PCH@1780000900.MediaA.change-to-a-promoted-requirement',
    target_id: 'REQ@1712870400.MediaB.every-write-is-verified-before-it-lands',
    target_name: 'Every write is verified before it lands',
    kind: 'entity' as const,
    changed_fields: ['summary'],
    state: 'draft' as const,
    condition: 'current' as const,
    divergence: [{
      field: 'summary',
      proposed: 'Every write is verified before it lands, including writes made by an agent.',
      current: 'Every write is verified before it lands.',
    }],
  },
  {
    artifact_id: 'PCH@1780000901.MediaC.change-to-a-promoted-standard',
    target_id: 'STD@1712870400.MediaD.naming-conventions-for-shared-content',
    target_name: 'Naming conventions for shared content',
    kind: 'document' as const,
    changed_fields: ['title'],
    state: 'submitted' as const,
    condition: 'stale' as const,
    divergence: [{
      field: 'title',
      proposed: 'Naming conventions for shared content',
      current: 'Naming conventions for promoted content',
    }],
  },
]

test('the changes an engagement is holding', async ({ page }) => {
  const problems = watch(page)
  await page.route('**/api/changes', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ changes: CHANGES, total: CHANGES.length }),
    })
  })

  await page.goto('/changes', { waitUntil: 'load' })

  // `.first()`: each name appears in its row and again in the values shown beneath it, which is
  // the page working rather than an ambiguity to design around.
  await expect(page.getByText('Every write is verified before it lands').first()).toBeVisible()
  await expect(page.getByText('Naming conventions for shared content').first()).toBeVisible()
  // Both readings on screen: the settled change and the one whose artifact has moved under it.
  await expect(page.getByText(/moved since this was written/i)).toBeVisible()
  await capture(page, 'proposed-changes.png', PROVENANCE)
  expect(problems, 'runtime problems while capturing proposed-changes.png').toEqual([])
})
