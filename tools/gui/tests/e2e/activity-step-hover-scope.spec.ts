import { test, expect } from './coverage-fixture'

/**
 * An activity step's label is one `<a href="arch://…">` PER TEXT RUN, not one per step:
 * PlantUML wraps a long label across lines and anchors each run separately, so a single
 * step in the dogfood repo arrives as more than twenty anchors. The renderer cannot fix
 * that — a standalone link clause renders the literal URL instead of the label — so the
 * viewer has to treat the mapped group as the unit.
 *
 * It did not. Hover was a CSS `:hover` on whatever element the pointer was over, which lit
 * up one word of a step and left the rest of the label and the step's own shape untouched.
 * Selection was already group-scoped; this asserts hover now agrees with it, and that
 * leaving the step clears the whole group rather than the one run.
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_diagram-collection', 'platform-core')
  })
})

test('hovering one run of a wrapped step label highlights the whole step', async ({ page }) => {
  await page.goto('/diagrams/ACT@1786234873.w_H9LsR.working-in-a-scratchpad-area')

  const svg = page.locator('.svg-wrap svg')
  await expect(svg).toBeVisible({ timeout: 20000 })

  // Any step whose label wrapped: the interesting case is precisely a >1-element group.
  const stepId = await page.evaluate(() => {
    const counts = new Map<string, number>()
    for (const el of Array.from(document.querySelectorAll('.svg-wrap [data-entity-id]'))) {
      const id = el.getAttribute('data-entity-id') ?? ''
      counts.set(id, (counts.get(id) ?? 0) + 1)
    }
    let best = ''
    let most = 0
    for (const [id, n] of counts) if (n > most) { best = id; most = n }
    return most > 1 ? best : ''
  })
  expect(stepId, 'no step maps to more than one SVG element — the defect cannot show here').not.toBe('')

  const parts = page.locator(`.svg-wrap [data-entity-id="${stepId}"]`)
  const total = await parts.count()
  expect(total).toBeGreaterThan(1)

  // Hover a label run rather than the step's shape: the runs sit on top of the shape, so
  // pointing at the shape is what the user cannot do — and it is one run lighting up alone
  // that this guards against.
  await page.locator(`.svg-wrap a[data-entity-id="${stepId}"]`).first().hover()
  await expect(page.locator(`.svg-wrap [data-entity-id="${stepId}"].svg-hovered`)).toHaveCount(total)
  // Scoped to the step, not the diagram: another step must not light up with it.
  await expect(
    page.locator(`.svg-wrap .svg-hovered:not([data-entity-id="${stepId}"])`),
  ).toHaveCount(0)

  await page.locator('.img-container').hover({ position: { x: 4, y: 4 } })
  await expect(page.locator('.svg-wrap .svg-hovered')).toHaveCount(0)
})
