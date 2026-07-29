import { describe, expect, it } from 'vitest'
import {
  domainOptionsForDomains,
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
