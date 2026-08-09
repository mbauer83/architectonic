import { expect, test } from '@playwright/test'
import { capture, watch, type CaptureProvenance } from './mediaHelpers'

/**
 * The README's picture of the scratchpad tier.
 *
 * Driven from a **committed fixture** rather than content the test invents, so the shot is
 * reproducible and the thing it shows is the thing the repository actually holds. The four notes
 * are the progression the tier exists for, side by side: one that has decided nothing, one narrowed
 * to its domain, one typed, and one bound to an element the model already had.
 */

const SCRATCHPAD = 'SCR@1786299627.Dnc28yf.q3-platform-thinking'

test('the scratchpad canvas, with a note at each stage of deciding', async ({ page }) => {
  const problems = watch(page)
  await page.goto(`/scratchpads/${encodeURIComponent(SCRATCHPAD)}`, { waitUntil: 'load' })

  await expect(page.locator('[data-testid="scratchpad-canvas"]')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.sp-note')).toHaveCount(4)
  // The progression is the subject: assert each stage is on screen rather than trusting the
  // fixture to have stayed as it was written.
  await expect(page.locator('.sp-note .sp-untyped')).toHaveCount(1)
  await expect(page.locator('.sp-note .sp-domain')).toHaveCount(1)
  await expect(page.locator('.sp-note.bound')).toHaveCount(1)
  await expect(page.locator('.sp-link.typed')).not.toHaveCount(0)

  const provenance: CaptureProvenance = {
    test_name: 'the scratchpad canvas, with a note at each stage of deciding',
    artifact_ids: [SCRATCHPAD],
    synthetic_augmentation: false,
  }
  await capture(page, 'scratchpad-hero.png', provenance)
  expect(problems).toEqual([])
})
