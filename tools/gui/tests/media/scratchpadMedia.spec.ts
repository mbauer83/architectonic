import { expect, test } from '@playwright/test'
import { capture, watch, type CaptureProvenance } from './mediaHelpers'

/**
 * The README's picture of the scratchpad tier.
 *
 * Taken against a **separate, disposable workspace** rather than this repository, and pointed at it
 * with `E2E_BASE_URL` and `HERO_SCRATCHPAD`. The reason is the fifth state: a *realized* note names
 * an entity a lift created, so it cannot be written by hand without putting a reference to nothing
 * into a file that claims otherwise — and producing one here would leave an entity in the
 * self-model that exists only to be photographed.
 *
 * Reproducible rather than hand-made: `tools/media/seed_scratchpad_hero.py` builds the fixture,
 * lift included, and its docstring carries the four commands that stand the workspace up.
 *
 * The subject is the progression the tier exists for, on a canvas that looks like it is being
 * thought on: sixteen notes, most undecided, and five stages side by side — nothing decided, a
 * domain, a type, a binding to an element that already existed, and one lifted into the model.
 */

const SCRATCHPAD = process.env.HERO_SCRATCHPAD ?? ''


test('the scratchpad canvas, with a note at each stage of deciding', async ({ page }) => {
  test.skip(!SCRATCHPAD, 'HERO_SCRATCHPAD is unset: see tools/media/seed_scratchpad_hero.py')
  const problems = watch(page)
  // Taller than the media default, so two frames fit — a shot of one frame cannot show a link
  // crossing between them, and those links are the argument for one canvas rather than four tabs.
  await page.setViewportSize({ width: 1440, height: 945 })
  await page.goto(`/scratchpads/${encodeURIComponent(SCRATCHPAD)}`, { waitUntil: 'load' })

  await expect(page.locator('[data-testid="scratchpad-canvas"]')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.sp-note')).toHaveCount(16)
  // The progression is the subject: assert each stage is on screen rather than trusting the
  // fixture to have stayed as it was written.
  await expect(page.locator('.sp-note .sp-untyped')).toHaveCount(6)
  await expect(page.locator('.sp-note .sp-domain')).toHaveCount(3)
  await expect(page.locator('.sp-note.bound')).toHaveCount(3)
  await expect(page.locator('.sp-note.realized')).toHaveCount(1)
  // Both frames on screen, and the links that cross between them.
  await expect(page.locator('.sp-area')).toHaveCount(4)
  await expect(page.locator('.sp-link:not(.drawing)')).toHaveCount(14)

  const provenance: CaptureProvenance = {
    test_name: 'the scratchpad canvas, with a note at each stage of deciding',
    artifact_ids: [SCRATCHPAD],
    // The workspace is seeded for the shot, which is the honest word for it — but every note,
    // link and the realization are produced through the product's own write path, not drawn.
    synthetic_augmentation: true,
  }
  await capture(page, 'scratchpad-hero.png', provenance)
  expect(problems).toEqual([])
})
