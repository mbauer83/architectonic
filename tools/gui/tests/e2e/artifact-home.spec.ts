import { expect, test } from '@playwright/test'

/**
 * Choosing where an artifact is filed, and arriving at the form already inside a collection.
 *
 * Driven against the real backend rather than intercepted: the whole subject is that the control is
 * populated from the repository's own collections, and a fixture list would assert the fixture.
 *
 * No collection is named in these assertions. The slugs belong to whichever repository the suite
 * runs against, so the spec reads the first one the control offers and navigates with that —
 * asserting the behaviour rather than the content, which is the rule for tests over live model
 * content.
 */

const homeSelect = (page: import('@playwright/test').Page) =>
  page.locator('select').filter({ has: page.locator('option', { hasText: 'No collection' }) }).first()

test.describe('where a new artifact is filed', () => {
  test('the form offers the repository’s collections', async ({ page }) => {
    await page.goto('/entities/new')

    const select = homeSelect(page)
    await expect(select).toBeVisible()
    await expect(select.locator('option')).not.toHaveCount(0)
  })

  test('nothing is chosen when the reader was not inside a collection', async ({ page }) => {
    await page.goto('/entities/new')

    await expect(homeSelect(page)).toHaveValue('')
  })

  test('the collection being browsed is what the form opens on', async ({ page }) => {
    await page.goto('/entities/new')
    const select = homeSelect(page)
    await expect(select).toBeVisible()
    const slugs = await select.locator('option').evaluateAll(
      (options) => options.map((option) => (option as HTMLOptionElement).value).filter(Boolean),
    )
    test.skip(slugs.length === 0, 'this repository has no model-project collections to file into')

    await page.goto(`/entities/new?group=${encodeURIComponent(slugs[0])}`)

    await expect(homeSelect(page)).toHaveValue(slugs[0])
  })

  test('a collection this kind is not filed on is not silently adopted', async ({ page }) => {
    // Four axes exist and they are independent registries. Defaulting to a slug the control cannot
    // show would set the form to a home the reader can neither see nor change.
    await page.goto('/entities/new?group=not-a-model-project')

    await expect(homeSelect(page)).toHaveValue('')
  })
})
