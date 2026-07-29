import { type APIRequestContext } from '@playwright/test'
import { test, expect } from './coverage-fixture'

/**
 * Pinning a viewpoint definition from the management list surfaces it in Home's
 * quick-access section, and following that link executes it on its representation-
 * appropriate surface — same routing the management list's own "Execute" button uses.
 */

const resetPins = (request: APIRequestContext) =>
  request.put('/api/viewpoints/pins', { data: { slugs: [] } })

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
  })
})

test.afterEach(async ({ request }) => {
  await resetPins(request)
})

test('pinning a definition surfaces it on Home and unpinning removes it again', async ({ page, request }) => {
  await resetPins(request)

  await page.goto('/viewpoints')
  const row = page.locator('tr', { hasText: 'goal-realization' })
  await expect(row.getByRole('button', { name: 'Pin goal-realization' })).toBeVisible()
  await row.getByRole('button', { name: 'Pin goal-realization' }).click()
  await expect(row.getByRole('button', { name: 'Unpin goal-realization' })).toBeVisible()

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Pinned Viewpoints' })).toBeVisible()
  const pinnedLink = page.getByRole('link', { name: /Goal Realization/ })
  await expect(pinnedLink).toBeVisible()
  await expect(pinnedLink).toHaveAttribute('href', '/graph?viewpoint=goal-realization')

  await pinnedLink.click()
  await expect(page).toHaveURL(/\/graph\?viewpoint=goal-realization/)

  await page.goto('/viewpoints')
  await page.locator('tr', { hasText: 'goal-realization' }).getByRole('button', { name: 'Unpin goal-realization' }).click()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Pinned Viewpoints' })).toHaveCount(0)
})

test('a diagram-representation pin routes Home straight to the diagram surface', async ({ page, request }) => {
  await resetPins(request)

  await page.goto('/viewpoints')
  await page.locator('tr', { hasText: 'application-structure' }).getByRole('button', { name: 'Pin application-structure' }).click()

  await page.goto('/')
  const pinnedLink = page.getByRole('link', { name: /Application Structure/ })
  await expect(pinnedLink).toHaveAttribute('href', '/viewpoints/diagram?viewpoint=application-structure')
  await pinnedLink.click()
  await expect(page).toHaveURL(/\/viewpoints\/diagram\?viewpoint=application-structure/)
  await expect(page.getByRole('heading', { name: /Application Structure \(application-structure\) — diagram/ })).toBeVisible()
})
