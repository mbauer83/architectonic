import { describe, expect, it } from 'vitest'

import {
  emptyMessage, groupByComponent, parseProvenance, severityRank,
  vulnerabilityKey, vulnerabilityLabel, withheldNote,
  type SecurityFinding,
} from '../SecurityFindingsView.helpers'

const finding = (over: Partial<SecurityFinding> = {}): SecurityFinding => ({
  finding_id: 'FND@1',
  canonical_vulnerability_id: 'VID@abc',
  severity_band: 'high',
  cvss_score: 8.1,
  component_name: 'urllib3',
  component_purl: 'pkg:pypi/urllib3@1',
  component_directness: 'direct',
  ...over,
})

describe('vulnerability identity', () => {
  it('shows the feed id an analyst recognises', () => {
    expect(vulnerabilityLabel(finding({
      provenance: '{"osv_id":"CVE-2026-1","source":"osv"}',
    }))).toBe('CVE-2026-1')
  })

  it('falls back to the canonical id when provenance names no feed id', () => {
    expect(vulnerabilityLabel(finding({ provenance: null }))).toBe('VID@abc')
  })

  it('navigates by the canonical id, never the feed id', () => {
    /* The feed id is one of several aliases; the canonical id resolves whichever
       alias the scanner happened to report. */
    expect(vulnerabilityKey(finding({
      provenance: '{"osv_id":"CVE-2026-1"}',
    }))).toBe('VID@abc')
  })

  it('survives malformed provenance rather than breaking the view', () => {
    expect(parseProvenance(finding({ provenance: '{not json' }))).toEqual({})
    expect(vulnerabilityLabel(finding({ provenance: '{not json' }))).toBe('VID@abc')
  })
})

describe('severityRank', () => {
  it('orders bands ascending and sinks the unknown', () => {
    expect(severityRank('critical')).toBeGreaterThan(severityRank('high'))
    expect(severityRank('low')).toBeGreaterThan(severityRank('none'))
    expect(severityRank(null)).toBeLessThan(severityRank('none'))
  })
})

describe('groupByComponent', () => {
  it('groups findings under the component they affect', () => {
    const groups = groupByComponent([
      finding({ finding_id: 'a', component_name: 'urllib3', component_purl: 'p1' }),
      finding({ finding_id: 'b', component_name: 'urllib3', component_purl: 'p1' }),
      finding({ finding_id: 'c', component_name: 'idna', component_purl: 'p2' }),
    ])

    expect(groups).toHaveLength(2)
    expect(groups.flatMap((g) => g.findings)).toHaveLength(3)
  })

  it('puts the worst component first so attention lands where it is needed', () => {
    const groups = groupByComponent([
      finding({ component_name: 'mild', component_purl: 'p1', severity_band: 'low' }),
      finding({ component_name: 'severe', component_purl: 'p2', severity_band: 'critical' }),
    ])

    expect(groups.map((g) => g.componentName)).toEqual(['severe', 'mild'])
    expect(groups[0].maxSeverityBand).toBe('critical')
  })

  it('orders findings within a component worst-first', () => {
    const groups = groupByComponent([
      finding({ finding_id: 'a', severity_band: 'low' }),
      finding({ finding_id: 'b', severity_band: 'critical' }),
      finding({ finding_id: 'c', severity_band: 'medium' }),
    ])

    expect(groups[0].findings.map((f) => f.severity_band))
      .toEqual(['critical', 'medium', 'low'])
  })
})

describe('withheld and empty states', () => {
  it('always surfaces withheld records', () => {
    /* A filtered list that looks complete is the failure exposure filtering must
       not produce. */
    expect(withheldNote({ findings: [], withheld: 3 })).toMatch(/3 records/)
    expect(withheldNote({ findings: [], withheld: 1 })).toMatch(/1 record /)
    expect(withheldNote({ findings: [], withheld: 0 })).toBeNull()
  })

  it('distinguishes "nothing found" from "nothing you may see"', () => {
    expect(emptyMessage({ findings: [], withheld: 0 })).toMatch(/No vulnerability findings/)
    expect(emptyMessage({ findings: [], withheld: 2 })).toMatch(/visible at your classification/)
  })

  it('is silent when there are findings to show', () => {
    expect(emptyMessage({ findings: [finding()], withheld: 0 })).toBeNull()
  })

  it('prefers an explicit backend reason', () => {
    expect(emptyMessage({ findings: [], reason: 'no co-located signals store' }))
      .toBe('no co-located signals store')
  })
})
