import { test, expect } from './coverage-fixture'

/**
 * The proposed-changes surface, driven in a browser.
 *
 * Editing an artifact this repository does not own records a change awaiting review upstream. What
 * this covers is everything a person does with one: see what they are holding, read what a stale
 * change would make the artifact say, bring it onto the current version, and take it back.
 *
 * The API is intercepted rather than driven, because the browser suite runs against the developer's
 * own repository and a spec that recorded a real change would write into it. The write path itself
 * is covered where it can be: the REST and MCP write walks drive it against a fixture backend, with
 * a real worktree and the real verifier. What only a browser can answer is what the page does with
 * the answer — which is what these assert.
 */

const CHANGE = {
  artifact_id: 'PCH@1780000900.SpecAaa.change-to-a-promoted-requirement',
  target_id: 'REQ@1712870400.SpecBbb.a-promoted-requirement',
  target_name: 'A promoted requirement',
  kind: 'entity' as const,
  changed_fields: ['summary'],
  state: 'draft' as const,
  condition: 'current' as const,
  divergence: [{ field: 'summary', proposed: 'My wording.', current: 'The enterprise wording.' }],
}

const serve = async (page: import('@playwright/test').Page, changes: unknown[]) => {
  await page.route('**/api/changes', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ changes, total: changes.length }),
    })
  })
}

test.describe('what an author is holding', () => {
  test('says so plainly when nothing is proposed', async ({ page }) => {
    await serve(page, [])
    await page.goto('/changes')

    await expect(page.getByText(/Nothing changed yet/i)).toBeVisible()
  })

  test('names the artifact, not the change record', async ({ page }) => {
    await serve(page, [CHANGE])
    await page.goto('/changes')

    await expect(page.getByRole('link', { name: 'A promoted requirement' })).toBeVisible()
    await expect(page.getByText(CHANGE.artifact_id)).toHaveCount(0)
  })

  test('links the promoted artifact, never the internal reference', async ({ page }) => {
    await serve(page, [CHANGE])
    await page.goto('/changes')

    const href = await page.getByRole('link', { name: 'A promoted requirement' }).getAttribute('href')
    expect(href).toContain('REQ%40')
    expect(href).not.toContain('GAR%40')
  })

  test('says which fields it changes and whether anyone has been asked', async ({ page }) => {
    await serve(page, [CHANGE])
    await page.goto('/changes')

    await expect(page.getByText('summary', { exact: true }).first()).toBeVisible()
    await expect(page.getByText(/Not sent for review yet/i)).toBeVisible()
  })

  test('shows both values, so a reader sees what the change would make it say', async ({ page }) => {
    await serve(page, [CHANGE])
    await page.goto('/changes')

    await expect(page.getByText('The enterprise wording.')).toBeVisible()
    await expect(page.getByText('My wording.')).toBeVisible()
  })
})

test.describe('a change whose artifact has moved', () => {
  const stale = { ...CHANGE, condition: 'stale' as const }

  test('says the artifact moved, in words rather than by colour', async ({ page }) => {
    await serve(page, [stale])
    await page.goto('/changes')

    await expect(page.getByText(/has moved since this was written/i)).toBeVisible()
  })

  test('offers to bring it onto the current version', async ({ page }) => {
    await serve(page, [stale])
    await page.goto('/changes')

    await expect(page.getByRole('button', { name: /Bring onto the current version/i })).toBeVisible()
  })

  test('does not offer that on a change that already sits on it', async ({ page }) => {
    await serve(page, [CHANGE])
    await page.goto('/changes')

    await expect(page.getByRole('button', { name: /Bring onto the current version/i })).toHaveCount(0)
  })

  test('reports what the rebase concluded beside the row', async ({ page }) => {
    await serve(page, [stale])
    await page.route('**/api/changes/*/rebase', async (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          changes: [{
            artifact_id: stale.artifact_id, target_id: stale.target_id,
            outcome: 'conflicting', reason: 'E031: the display section is missing', restamped: false,
          }],
          summary: '0 clean, 0 already upstream, 1 conflicting; 0 restamped',
        }),
      }))
    await page.goto('/changes')

    await page.getByRole('button', { name: /Bring onto the current version/i }).click()

    await expect(page.getByText(/E031: the display section is missing/)).toBeVisible()
    await expect(page.getByText(/nothing was written/i)).toBeVisible()
  })
})

test.describe('taking a change back', () => {
  test('discards the one that was asked for, and stops listing it', async ({ page }) => {
    let discarded: string | null = null
    await page.route('**/api/changes/*', async (route) => {
      if (route.request().method() !== 'DELETE') return route.fallback()
      discarded = route.request().url()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ artifact_id: CHANGE.artifact_id, discarded: true, state: 'abandoned' }),
      })
    })
    let served = [CHANGE] as unknown[]
    await page.route('**/api/changes', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      const body = JSON.stringify({ changes: served, total: served.length })
      served = []
      await route.fulfill({ status: 200, contentType: 'application/json', body })
    })
    await page.goto('/changes')

    await page.getByRole('button', { name: 'Discard' }).click()

    await expect(page.getByText(/Nothing changed yet/i)).toBeVisible()
    expect(discarded).toContain('PCH%40')
  })
})

test.describe('the page is reachable the way a person finds it', () => {
  test('the primary navigation offers it, and does not call it "Changes"', async ({ page }) => {
    await serve(page, [])
    await page.goto('/entities')

    const nav = page.locator('nav[aria-label="Primary"]')
    await expect(nav.getByRole('link', { name: 'Proposed' })).toBeVisible()
    // The workflow cluster's own "Changes" control is the git save flow; one label for both would
    // make them indistinguishable at the moment of clicking.
    await expect(nav.getByRole('link', { name: 'Changes', exact: true })).toHaveCount(0)
  })
})
