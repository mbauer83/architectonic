import { expect, test } from '@playwright/test'

const BACKEND = 'APP@1777293133.OYEmP1.architecture-backend'

test('an existing relationship opens in the integrated editor', async ({ page }) => {
  await page.goto(`/entities/${encodeURIComponent(BACKEND)}`)

  const relationship = page.locator('.conn-item-wrap').filter({
    has: page.getByRole('link', { name: 'REST Interface', exact: true }),
  })
  await expect(relationship).toBeVisible()
  await relationship.locator('button[title="Edit relationship"]').click()

  // The wiring this covers: the form opens populated from the stored relationship, so a
  // description that never reached the form would show up here as an empty textbox. Asserted as
  // "carries the stored prose", never as the prose itself — rewording a description in the model
  // is authoring, and a test that fails on it reports a regression that did not happen.
  await expect(relationship.getByLabel('Description')).toHaveValue(/\S/)
  await expect(relationship.getByRole('button', { name: 'Save relationship' })).toBeVisible()

  // `serving` declares no metadata profile, and a profile-less type must render no properties
  // section at all rather than an empty one. The composable's unit tests cover the branch where
  // a profile exists; no connection type in this repository declares one.
  await expect(relationship.getByText('Relationship properties', { exact: true })).toHaveCount(0)
})

test('relationship target search offers candidates as soon as it receives focus', async ({ page }) => {
  await page.goto(`/entities/${encodeURIComponent(BACKEND)}`)

  const outgoing = page.locator('.conn-panel').filter({
    has: page.getByRole('heading', { name: 'Outgoing connections', exact: true }),
  })
  const targetGroup = outgoing.locator('.type-group').filter({
    has: page.getByText('application-interface', { exact: true }),
  })
  await targetGroup.locator('button[title="Add connection"]').click()
  const search = targetGroup.getByPlaceholder('Search target entity...')
  await search.focus()

  await expect(targetGroup.locator('.ep-drop')).toBeVisible()
  await expect(targetGroup.locator('.ep-drop').getByText('REST Interface', { exact: true })).toBeVisible()
})
