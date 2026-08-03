import { test, expect } from '@playwright/test'

/**
 * A domain card on Home reports a repository-wide count, so its link must open a repository-wide list.
 *
 * `/api/stats` is documented as "Repository-wide artifact counts" and takes no collection, so the
 * number on a card is every entity in that domain. The link carried only `?domain=`, and `EntitiesView`
 * fills an absent `?group=` from the collection last browsed — so the card said one thing and the
 * destination showed another: click Motivation after working inside a project and you get that
 * project's motivation entities, which is usually none of them.
 *
 * The absence of this spec is why it shipped. Nothing in the browser suite clicked a domain card, and
 * no unit test can see the interaction: the count comes from one surface, the narrowing from another,
 * and each is correct alone.
 *
 * Content-independent on purpose. It never asserts how many entities a domain or a collection holds —
 * authoring either is the product working. What it asserts is that the scope the card promised is the
 * scope that opens.
 */
test('a domain card opens every collection, not the one last browsed', async ({ page }) => {
  // ── Arrange: browse inside a collection, which is what gets remembered ──────────────────────────
  await page.goto('/entities/groups')

  // Any real project; the fixture for this spec is whatever the repository holds, so it takes the
  // first one rather than naming one that authoring could rename or retire.
  const firstProject = page.locator('.tree-btn--project').nth(1)
  await expect(firstProject).toBeVisible()
  const projectName = (await firstProject.locator('.node-label').textContent())?.trim() ?? ''
  expect(projectName).not.toBe('')

  await firstProject.click()
  await expect(page).toHaveURL(/[?&]group=/)
  // The collection is now both selected and persisted; this is the state the bug needed.
  await expect(page.locator('.tree-btn--project.active .node-label')).toHaveText(projectName)

  // ── Act: Home, then a domain card ──────────────────────────────────────────────────────────────
  await page.goto('/')
  const card = page.locator('.card--domain').first()
  await expect(card).toBeVisible()
  const cardDomain = (await card.locator('.domain-name').textContent())?.trim() ?? ''
  expect(cardDomain).not.toBe('')

  await card.click()

  // ── Assert: the destination is the scope the card counted ──────────────────────────────────────
  await expect(page).toHaveURL(/[?&]domain=/)
  // Not the collection that was being browsed. Asserted on the URL *and* on what the tree shows
  // active, because the two came apart in different ways: the query is what a bookmark carries and
  // the tree is what the reader believes.
  await expect(page).not.toHaveURL(new RegExp(`[?&]group=(?!all)`))
  await expect(page.locator('.tree-btn--project.active')).toHaveText('All')
})

test('a collection stays selected when browsing within it', async ({ page }) => {
  /**
   * The other half, and the reason the fix is a link-side decision rather than deleting the restore.
   *
   * `NavBar`'s browse link and `EntityDetailView`'s back link both carry `domain`/`view`/`type` and
   * drop `group`, and it is the same saved-preference restore that keeps you inside the collection you
   * were reading. Removing that to fix the card would have broken this, so this spec exists to fail if
   * a later change reaches for the simpler fix.
   */
  await page.goto('/entities/groups')
  const firstProject = page.locator('.tree-btn--project').nth(1)
  await expect(firstProject).toBeVisible()
  const projectName = (await firstProject.locator('.node-label').textContent())?.trim() ?? ''
  await firstProject.click()
  await expect(page.locator('.tree-btn--project.active .node-label')).toHaveText(projectName)

  // Follow the in-app browse link, which carries no `group`.
  await page.goto('/entities')

  await expect(page.locator('.tree-btn--project.active .node-label')).toHaveText(projectName)
})
