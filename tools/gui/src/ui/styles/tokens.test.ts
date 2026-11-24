import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * The dark values are written twice in `tokens.css` — once for the system setting, once for an explicit
 * choice — because CSS cannot name one block from both. These hold the two copies to one meaning, and
 * hold the paper out of the theme.
 */
const css = readFileSync(join(import.meta.dirname, 'tokens.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')

const declarations = (body: string): Map<string, string> =>
  new Map([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]))

const blockAfter = (opener: string): Map<string, string> => {
  const start = css.indexOf(opener)
  expect(start, `${opener} is declared`).toBeGreaterThanOrEqual(0)
  const open = css.indexOf('{', start + opener.length - 1)
  const close = css.indexOf('}', open)
  return declarations(css.slice(open + 1, close))
}

const light = blockAfter(':root {')
const systemDark = blockAfter(':root:not([data-theme="light"]) {')
const chosenDark = blockAfter(':root[data-theme="dark"] {')

describe('the theme tokens', () => {
  it('give the system dark setting and the explicit dark choice the same values', () => {
    expect(Object.fromEntries(chosenDark)).toEqual(Object.fromEntries(systemDark))
  })

  it('declare a light value for every token the dark theme redefines', () => {
    const missing = [...chosenDark.keys()].filter((name) => !light.has(name))
    expect(missing).toEqual([])
  })

  it('keep the diagram paper and the layer colours out of the dark theme', () => {
    const paperOrLayer = (name: string) => ['--paper', '--on-paper'].includes(name) || name.startsWith('--domain-')
    const themed = [...chosenDark.keys()].filter(paperOrLayer)
    expect(themed).toEqual([])
    expect(light.get('--paper')).toBe('#fafafa')
  })

  it('switch the browser controls with the theme', () => {
    expect(css).toMatch(/:root\[data-theme="dark"\][^}]*color-scheme: dark/)
    expect(css).toMatch(/:root:not\(\[data-theme="light"\]\)[^}]*color-scheme: dark/)
  })
})
