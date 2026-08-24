import { expect, test } from '@playwright/test'

/**
 * The page the nav's "Security findings" entry reaches.
 *
 * It reached `SecurityFindingsView`, which needs an entity id to read anything: with none it drew
 * its header — *Active signal snapshot for* — followed by an empty link, and nothing else. A
 * sentence fragment behind a nav entry that offers a working page, found by a reader opening it.
 *
 * The unanchored list address the nav was written against is retired: a finding belongs to an entity
 * and the read that returns one is a subresource of that entity. So the anchors are the answer, and
 * this asserts the fragment is gone rather than only that the page has content — a page can have
 * content and still leave that sentence hanging above it.
 */

test.describe('the security findings index', () => {
  test('offers the anchors rather than a header with no anchor to name', async ({ page }) => {
    await page.goto('/assurance/security-findings')

    await expect(page.getByRole('heading', { name: 'Security findings' })).toBeVisible()
    // The fragment. Asserted as absent from the whole body, because that is how it appeared.
    await expect(page.locator('body')).not.toContainText('Active signal snapshot for')
  })

  test('says which of the two empty situations it is in', async ({ page }) => {
    await page.goto('/assurance/security-findings')
    await expect(page.getByRole('heading', { name: 'Security findings' })).toBeVisible()

    const rows = page.getByTestId('assessed-entity-row')
    const noSnapshots = page.getByTestId('no-snapshots')
    const noneActive = page.getByTestId('no-assessed-entities')

    // Whichever the store is in, the page states it — and never leaves all three absent, which is
    // what an empty render looks like.
    await expect
      .poll(async () => (await rows.count()) + (await noSnapshots.count()) + (await noneActive.count()))
      .toBeGreaterThan(0)
  })

  test('the nav entry leads here', async ({ page }) => {
    await page.goto('/assurance')

    await page.getByRole('link', { name: 'Security findings' }).first().click()

    await expect(page).toHaveURL(/\/assurance\/security-findings$/)
    await expect(page.locator('body')).not.toContainText('Active signal snapshot for')
  })
})
