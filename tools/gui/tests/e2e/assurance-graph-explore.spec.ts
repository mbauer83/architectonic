import { expect, test } from '@playwright/test'

const HAZARD = 'HAZ@1784721764.wra3.48aefe'
const UCA_NAME = 'Renderer is given an untrusted PUML body carrying a file/network preprocessor directive'

test('a real assurance neighborhood supports deep-linking, expansion, selection, and zoom', async ({ page }) => {
  await page.goto(`/assurance/nodes/${encodeURIComponent(HAZARD)}/graph`)

  await expect(page.getByText('Assurance Graph', { exact: true })).toBeVisible()
  // Counted relative to whatever the model holds, never pinned to a number. This hazard's
  // neighbourhood grows whenever someone records a failure mode that leads to it — which is the
  // analysis working, not a regression — and an exact count turns that into a test failure. What the
  // test is actually about is that a deep link resolves to a neighbourhood, expansion adds to it, and
  // selection describes what was clicked.
  //
  // Edges are counted rather than visibility-checked: an edge is an SVG <g> wrapping a stroked
  // path, so it has no layout box of its own and reports hidden even while drawn.
  const nodes = page.locator('.graph-node')
  await expect(nodes).not.toHaveCount(0, { timeout: 15_000 })
  await expect(page.locator('.graph-edge')).not.toHaveCount(0)
  await expect(page.locator('.graph-sidebar')).toContainText('Renderer processes an untrusted PUML body')

  const beforeExpansion = await nodes.count()
  expect(beforeExpansion, 'a deep link must resolve to a neighbourhood, not a lone node')
    .toBeGreaterThan(1)

  const unsafeControlAction = nodes.filter({ hasText: UCA_NAME })
  await expect(unsafeControlAction).toBeVisible()
  await unsafeControlAction.dblclick()
  await expect.poll(() => nodes.count(), {
    message: 'expanding a node must add its own neighbours to the graph',
    timeout: 15_000,
  }).toBeGreaterThan(beforeExpansion)

  await unsafeControlAction.click()
  await expect(page.locator('.graph-sidebar')).toContainText(UCA_NAME)
  const detailsLink = page.locator('.graph-sidebar').getByRole('link', { name: UCA_NAME, exact: true })
  await expect(detailsLink).toHaveAttribute('href', /^\/assurance\/nodes\//)
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await page.getByRole('button', { name: 'Fit to view' }).click()
  await detailsLink.click()
  await expect(page).toHaveURL(/\/assurance\/nodes\//)
})
