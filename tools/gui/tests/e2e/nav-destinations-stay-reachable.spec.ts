/**
 * Every destination in the primary navigation is fully drawn and clickable at every
 * ordinary window width.
 *
 * The bar used to be laid out the other way round: the status cluster and the search box
 * kept their size and the links were the designated shrink victim, clipped by an
 * `overflow: hidden` on their container. That is invisible until the links outgrow the
 * space — and then it fails silently and badly. Adding one destination took the row past
 * 1440px, the ordinary laptop width, where "Viewpoints" was cut mid-word and Assurance was
 * not painted at all: a whole section of the product with no way in, on the developers' own
 * screens, found by looking at a screenshot rather than by any gate.
 *
 * Nothing catches this below the browser. The elements are laid out at their full size and
 * report it — `scrollWidth === clientWidth`, no ellipsis, correct text content — because it
 * is the *parent* that clips them. Only their geometry against the window, and a hit test
 * at the point a reader would click, tell the truth.
 *
 * How much room the bar has left depends on the status chip, and its sentence is repository
 * state, so measuring whatever it says today tests nothing: the first version of this file did
 * that and passed at 1440px against the broken layout — the very width the defect was found at.
 * It measures the chip at the widest the stylesheet permits instead, and asserts the invariant
 * that has to survive it: the status yields, every destination stays whole.
 */
import { expect, test } from '@playwright/test'

/** Laptop widths that ship: the smallest common panel, 720p, the two 16:9 defaults. */
const WIDTHS = [1280, 1366, 1440, 1600]

type Destination = {
  text: string
  clipped: boolean
  offWindow: boolean
  cutByAnAncestor: boolean
  hitTestsToItself: boolean
}

const DESTINATIONS = (): Destination[] => {
  // Widen the status chip to the widest the design permits before measuring. Its sentence is
  // repository state — on a clean checkout it is short and everything fits at any width — and
  // writing a long one into it does not hold, because the next render puts the real one back.
  // Its own max-width is the worst case the layout has to survive, and it is a fact about the
  // stylesheet rather than about today's content.
  const chip = document.querySelector<HTMLElement>('.cluster__status')
  if (chip !== null) chip.style.width = getComputedStyle(chip).maxWidth

  /**
   * Whether any ancestor that clips cuts this box. This is the check the defect needed and the
   * one an obvious test omits: a link inside an `overflow: hidden` parent reports its full box,
   * inside the window, with no ellipsis — the pixels are simply never painted. Measuring the
   * link alone says everything is fine while half a destination is missing from the screen.
   */
  const cutByAnAncestor = (el: Element): boolean => {
    const box = el.getBoundingClientRect()
    for (let p = el.parentElement; p !== null; p = p.parentElement) {
      const overflow = getComputedStyle(p)
      if (overflow.overflowX === 'visible' && overflow.overflowY === 'visible') continue
      const clip = p.getBoundingClientRect()
      if (box.left < clip.left - 0.5 || box.right > clip.right + 0.5) return true
    }
    return false
  }

  return [...document.querySelectorAll('.nav__links a')].map((el) => {
    const box = el.getBoundingClientRect()
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)
    return {
      text: (el.textContent ?? '').trim(),
      clipped: el.scrollWidth > el.clientWidth + 1,
      offWindow: box.left < -0.5 || box.right > window.innerWidth + 0.5 || box.width < 1,
      cutByAnAncestor: cutByAnAncestor(el),
      hitTestsToItself: hit !== null && (hit === el || el.contains(hit)),
    }
  })
}

test.describe('primary navigation', () => {
  for (const width of WIDTHS) {
    test(`every destination is reachable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/')
      await expect(page.locator('.nav__links a').first()).toBeVisible()

      const destinations = await page.evaluate(DESTINATIONS)
      expect(destinations.length).toBeGreaterThan(3)
      const unreachable = destinations.filter(
        (d) => d.clipped || d.offWindow || d.cutByAnAncestor || !d.hitTestsToItself,
      )
      expect(unreachable).toEqual([])

      // The bar yields by shrinking what it may, never by pushing the page sideways.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      )
      expect(overflow).toBeLessThanOrEqual(0)
    })
  }
})
