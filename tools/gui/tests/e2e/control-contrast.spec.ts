/**
 * No control may render text the reader cannot see.
 *
 * This exists because the same mistake was made three times independently, in three
 * components, and none of them was caught by review or by a passing test suite. The shape is
 * always the same: a shared rule sets a light background for a family of buttons, a variant
 * rule sets a light label for the selected one, and the shared rule outranks the variant —
 * `.prompt-actions button` (0,1,1) over `.primary-btn` (0,1,0), or a bare `:hover` over a
 * single-class active rule. The selector wins, the colour pair loses, and the label vanishes.
 * A component test cannot see it: the styles are individually reasonable and only the
 * resolved cascade is wrong.
 *
 * So this measures the resolved cascade. Every visible labelled control on every principal
 * route, in its default state and under the pointer, must clear a contrast floor against
 * whatever it is actually painted on.
 */
import { expect, test, type Page } from '@playwright/test'

/** WCAG relative luminance and contrast, evaluated in the page against computed styles. */
const SWEEP = (): Array<{ text: string; className: string; ratio: number; color: string }> => {
  const luminance = (css: string): number | null => {
    const match = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(css)
    if (match === null) return null
    const alpha = match[4] === undefined ? 1 : Number(match[4])
    if (alpha < 0.05) return null // transparent: the backdrop behind it is what shows
    const channel = (value: number): number => {
      const s = value / 255
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
    }
    return 0.2126 * channel(Number(match[1]))
      + 0.7152 * channel(Number(match[2]))
      + 0.0722 * channel(Number(match[3]))
  }
  const paintedOn = (element: Element): number => {
    let node: Element | null = element
    while (node !== null) {
      const value = luminance(getComputedStyle(node).backgroundColor)
      if (value !== null) return value
      node = node.parentElement
    }
    return 1 // nothing opaque all the way up: the page is white
  }
  const found: Array<{ text: string; className: string; ratio: number; color: string }> = []
  for (const element of document.querySelectorAll('button, a, [role="button"]')) {
    const text = (element.textContent ?? '').trim()
    if (text === '' || (element as HTMLElement).offsetParent === null) continue
    // Disabled controls are deliberately muted and WCAG exempts them: a greyed-out label is
    // the signal, not a defect. Including them would only teach readers to ignore this list.
    if ((element as HTMLButtonElement).disabled || element.getAttribute('aria-disabled') === 'true') continue
    const foreground = luminance(getComputedStyle(element).color)
    if (foreground === null) continue
    const background = paintedOn(element)
    const ratio = (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05)
    if (ratio < 2.0) {
      found.push({
        text: text.slice(0, 40),
        className: String((element as HTMLElement).className),
        ratio: Math.round(ratio * 100) / 100,
        color: getComputedStyle(element).color,
      })
    }
  }
  return found
}

/**
 * A floor, not the WCAG AA target of 4.5.
 *
 * The bug being prevented is a control that is *invisible* — ratios of 1.0 to 1.4. Setting
 * the bar at AA would fail a long tail of deliberately muted secondary text and turn this
 * into a suppression list nobody reads. 2.0 is unambiguously "the label is not there".
 */
const FLOOR = 2.0

const describe = (findings: Array<{ text: string; className: string; ratio: number }>): string =>
  findings.map((f) => `  "${f.text}" [${f.className}] ratio ${f.ratio}`).join('\n')

const sweepWithHover = async (page: Page): Promise<Array<{ text: string; className: string; ratio: number }>> => {
  const findings = await page.evaluate(SWEEP)
  // Hover matters on its own: a `:hover` background rule that outranks the selected-state rule
  // only produces the invisible label while the pointer is on the control.
  for (const button of (await page.locator('button:visible').all()).slice(0, 40)) {
    try {
      await button.hover({ timeout: 800 })
    } catch {
      continue // scrolled out from under us; the resting-state sweep already covered it
    }
    findings.push(...await page.evaluate(SWEEP))
  }
  const unique = new Map(findings.map((f) => [`${f.text}|${f.className}`, f]))
  return [...unique.values()]
}

const ROUTES = [
  '/', '/entities', '/entities/groups', '/viewpoints', '/viewpoints/query',
  '/diagrams', '/documents', '/search?q=graph', '/assurance', '/graph',
]

for (const route of ROUTES) {
  test(`every control on ${route} is legible`, async ({ page }) => {
    await page.goto(route, { waitUntil: 'load' })
    await page.waitForTimeout(1500)

    const findings = await sweepWithHover(page)

    expect(findings, `controls below the ${FLOOR}:1 floor:\n${describe(findings)}`).toEqual([])
  })
}

test('the viewpoint parameter prompt is legible', async ({ page }) => {
  // Reached only by running a parameterized viewpoint, so a route sweep never opens it — and
  // its confirm button is where this class of bug was found most recently.
  await page.goto('/viewpoints', { waitUntil: 'load' })
  // "needs input" is the catalog's own marker for a definition with required parameters —
  // exactly the ones whose Execute opens the prompt instead of running straight away.
  const row = page.locator('tr').filter({ has: page.locator('.needs-input') }).first()
  await expect(row, 'no parameterized viewpoint in this repository').toBeVisible({ timeout: 20_000 })
  await row.getByRole('button', { name: 'Execute' }).click()

  const panel = page.locator('.prompt-panel')
  await expect(panel).toBeVisible({ timeout: 20_000 })

  // Fill whatever it asks for: Run is disabled until every required parameter has a value, and
  // the sweep exempts disabled controls — so the confirm button is only under test once the
  // form is satisfiable. This is also the only state a user ever clicks it in.
  for (const box of await panel.locator('input[type="checkbox"]').all()) await box.check()
  for (const picker of await panel.locator('.ep-inp').all()) {
    await picker.fill('architecture')
    await panel.locator('.ep-result').first().click()
  }
  for (const field of await panel.locator('input:not([type="checkbox"]):not(.ep-inp)').all()) {
    if ((await field.inputValue()) === '') await field.fill('architecture')
  }
  await expect(panel.getByRole('button', { name: 'Run' })).toBeEnabled({ timeout: 10_000 })

  const findings = await sweepWithHover(page)

  expect(findings, `controls below the ${FLOOR}:1 floor:\n${describe(findings)}`).toEqual([])
})
