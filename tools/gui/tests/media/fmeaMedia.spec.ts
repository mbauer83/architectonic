/**
 * The failure-mode matrix, shot from the project's own analysis.
 *
 * Nothing is staged. The grid is the real self-analysis of the assurance access and rendering paths,
 * so the figure shows what the method actually produced: which elements were nominated and why, all
 * three cell states side by side, each factor with a glyph saying whether it was derived or asserted,
 * and the per-element roll-up. A synthetic fixture would have to invent priorities, which is the one
 * thing a figure about deriving priorities must not do.
 *
 * Separate from `media.spec.ts` for the reason `securityMedia.spec.ts` is: the manifest is reset once
 * there, and `record` merges by output path, so a sibling spec adds entries without clobbering.
 */
import { expect, test, type Page } from '@playwright/test'
import { capture, watch, type CaptureProvenance } from './mediaHelpers'

const ANALYSIS = 'FMEA@1785064654.x4kk.27b68b'
const BACKEND = 'APP@1777293133.OYEmP1.architecture-backend'
const STORE = 'APP@1780656431.E0fzqZ.confidential-assurance-store'
const KEYCHAIN = 'SSW@1780656477.OCX11y.os-keychain'

const provenance = (testName: string): CaptureProvenance => ({
  test_name: testName,
  artifact_ids: [ANALYSIS, BACKEND, STORE, KEYCHAIN],
  synthetic_augmentation: false,
})

/** Wait for the store gate to resolve, then for the grid itself rather than a fixed delay.
 *
 * Scoped to its analysis: there is one matrix per FMEA, and the unscoped page shows every analysis'
 * rows in one table — which is the defect the scoping fixed, not a thing to photograph. The old wait
 * for "Loading assurance store status" is gone with the hub page that rendered it; it had become a
 * no-op that passed instantly.
 */
async function openMatrix(page: Page): Promise<void> {
  await page.goto(`/assurance/fmea?analysis=${encodeURIComponent(ANALYSIS)}`, { waitUntil: 'load' })
  await expect(page.locator('.fmea-locked'), 'the store must be unlocked to shoot this figure')
    .toHaveCount(0)
  await expect(page.locator('.fmea-table')).toBeVisible({ timeout: 10_000 })
}

test('assurance FMEA matrix', async ({ page }) => {
  const problems = watch(page)
  await openMatrix(page)

  // Assert what the figure is meant to show before shooting it, so a regression produces a failed
  // test rather than a quietly less informative picture. Not an exact row count: nominating an
  // element is the product working, and a figure test that failed for it would report a false
  // regression far from whatever caused it.
  await expect(page.locator('.fmea-table tbody tr').first(), 'at least one nominated element')
    .toBeVisible()
  // Rows are named, not bare artifact ids — the whole point of the element heading.
  await expect(page.locator('.fmea-element-name').first()).not.toBeEmpty()
  await expect(page.locator('.cell-reason'), 'at least one cell dismissed as not credible')
    .not.toHaveCount(0)
  await expect(page.locator('.cell-factor'), 'recorded cells show their factors')
    .not.toHaveCount(0)
  await expect(page.locator('.cell-basis'), 'each factor says whether it was derived or asserted')
    .not.toHaveCount(0)

  await capture(page, 'assurance-fmea-matrix.png', provenance('assurance FMEA matrix'))
  expect(problems, 'runtime problems while capturing assurance-fmea-matrix.png').toEqual([])
})
