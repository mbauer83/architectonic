import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { DOMAIN_COLORS } from '../../../domain/types.generated'
import {
  domainOptionsForDomains,
  domainStyle,
  domainOptionsForModules,
  frameworkGroupsForModules,
  metaOntologyOptionsForModules,
} from '../domains'

describe('runtime module option filtering', () => {
  const archimateOnly = [{ name: 'archimate-4-0' }]
  const withSysml = [...archimateOnly, { name: 'sysml_v2_min' }]

  it('filters framework groups to active modules', () => {
    expect(frameworkGroupsForModules(archimateOnly).map((group) => group.key)).toEqual(['archimate-4'])
    expect(frameworkGroupsForModules(withSysml).map((group) => group.key)).toEqual([
      'archimate-4',
      'sysml-v2',
    ])
  })

  it('filters meta-ontology picker options to active modules', () => {
    expect(metaOntologyOptionsForModules(archimateOnly).map((option) => option.value)).toEqual([
      '',
      'archimate-4',
    ])
    expect(metaOntologyOptionsForModules(withSysml).map((option) => option.value)).toContain('sysml-v2')
  })

  it('filters domain options from active modules', () => {
    expect(domainOptionsForModules(archimateOnly).map((option) => option.key)).not.toContain('sysml')
    expect(domainOptionsForModules(withSysml).map((option) => option.key)).toContain('sysml')
  })

  it('filters domain options from active write-help domains', () => {
    expect(domainOptionsForDomains(['motivation', 'application']).map((option) => option.key)).toEqual([
      'motivation',
      'application',
    ])
  })
})

describe('the layer colours', () => {
  it('paint every declared domain with the ontology colour, and an undeclared one neutral', () => {
    for (const [domain, colour] of Object.entries(DOMAIN_COLORS))
      expect(domainStyle(domain)).toEqual({ '--domain': colour })
    expect(domainStyle('implementation')['--domain']).toBe(DOMAIN_COLORS.implementation)
    expect(domainStyle(undefined)['--domain']).toBe('#cbd5e1')
  })

  /** The incident: `tokens.css` carried a palette of its own (`#b6d7e1` against the ontology's
   * `#B0D0D9`, no implementation layer at all), and per-domain classes restated it in three files. */
  it('are spelled nowhere in the interface but the generated constants', () => {
    const root = join(import.meta.dirname, '..', '..', '..')
    const files = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) return entry.name === '__tests__' ? [] : files(path)
      return /\.(ts|vue|css)$/.test(entry.name) && !/\.(test|spec)\.ts$|generated\.ts$/.test(entry.name) ? [path] : []
    })
    const colours = Object.values(DOMAIN_COLORS).map((hex) => hex.toLowerCase())
    const offences = files(root).flatMap((path) => {
      const text = readFileSync(path, 'utf8')
      const lower = text.toLowerCase()
      return [
        ...colours.filter((hex) => lower.includes(hex)).map((hex) => `${path}: ${hex}`),
        ...[...text.matchAll(/--domain-[a-z]+\s*:|\.domain--[a-z]/g)].map((m) => `${path}: ${m[0]}`),
      ]
    })
    expect(offences).toEqual([])
  })
})
