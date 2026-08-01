/**
 * Marking a connection for removal has to be visible on the connection.
 *
 * The editor invites the click — "Click entity to mark for removal · Click connection to
 * toggle" — and the click does change state. If the diagram does not change with it, the
 * only feedback available says the edit did not happen, so the natural response is to click
 * again, which toggles it back off.
 *
 * Exercised end to end rather than in a unit test because the defect lived in DOM wiring:
 * the click handler was attached to each connection element while the element itself was
 * never registered in the map the highlight pass iterates. Every unit-testable part behaved.
 *
 * Connections are clicked by dispatching on the `<path>` rather than clicking the group. A
 * group's box around a long diagonal edge is mostly empty, so a positional click lands on the
 * background — not a descendant, so nothing bubbles to the handler. Dispatching on the
 * geometry is what a user hitting the line actually produces.
 */
import { expect, test } from '@playwright/test'

const DIAGRAM = 'ARC@1777452513.DM6OMl.motivation-chain-from-drivers-to-requirements'

test('a connection marked for removal is shown as marked, like an entity', async ({ page }) => {
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}/edit`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20_000 })

  const connection = page.locator('.svg-wrap [data-conn-id]').first()
  await expect(connection).toBeAttached({ timeout: 15_000 })
  await expect(connection).not.toHaveClass(/svg-remove/)

  await connection.locator('path').first().dispatchEvent('click')

  await expect(connection).toHaveClass(/svg-remove/)
})

test('an entity marked for removal is shown as marked', async ({ page }) => {
  // The behaviour the connection case is expected to match; pinned so the two cannot drift.
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}/edit`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20_000 })

  const entity = page.locator('.svg-wrap [data-entity-id]').first()
  await expect(entity).toBeAttached({ timeout: 15_000 })

  await entity.click({ force: true })

  await expect(entity).toHaveClass(/svg-remove/)
})

test('clicking a marked connection again clears the marking', async ({ page }) => {
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}/edit`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 20_000 })

  const connection = page.locator('.svg-wrap [data-conn-id]').first()
  await expect(connection).toBeAttached({ timeout: 15_000 })

  await connection.locator('path').first().dispatchEvent('click')
  await expect(connection).toHaveClass(/svg-remove/)
  await connection.locator('path').first().dispatchEvent('click')

  await expect(connection).not.toHaveClass(/svg-remove/)
})
