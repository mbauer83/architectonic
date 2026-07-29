import { describe, it, expect } from 'vitest'
import {
  SUPPLY_STEPS,
  ADMISSIBLE_ANCHOR_TYPES,
  summariseSeverities,
} from '../AssuranceSupplyChainWizard.helpers'

describe('SUPPLY_STEPS', () => {
  it('runs Scope → Ingest SBOM → Components → Vulnerabilities → Posture & VEX → AI-BOM', () => {
    expect(SUPPLY_STEPS.map((s) => s.key)).toEqual([
      'scope', 'ingest', 'components', 'vulnerabilities', 'posture', 'aibom',
    ])
  })

  it('offers ingest in the GUI, through the same gated command as every surface', () => {
    /* The browser is another adapter over IngestSecuritySignals, not a bypass:
       a CycloneDX document carries its generator in metadata.tools and the
       request id is supplied by the form or generated server-side. */
    expect(SUPPLY_STEPS.map((s) => s.key)).toContain('ingest')
  })

  it('gates the SBOM steps on an anchor; scope and aibom are anchor-free', () => {
    expect(SUPPLY_STEPS.find((s) => s.key === 'scope')?.needsAnchor).toBe(false)
    // AI-BOM is store-/architecture-wide (scan, export), so not anchor-gated.
    expect(SUPPLY_STEPS.find((s) => s.key === 'aibom')?.needsAnchor).toBe(false)
    const anchorGated = SUPPLY_STEPS.filter((s) => s.key !== 'scope' && s.key !== 'aibom')
    expect(anchorGated.every((s) => s.needsAnchor)).toBe(true)
  })

  it('admits the types that ship a bill of materials (never C4 container/system)', () => {
    /* An SBOM describes one built, independently shipped artifact: an application
       component, a technology node, or system software. Aggregates like grouping
       and application-collaboration do not ship as one thing. The backend owns
       this list and additionally restricts by specialization; a Python test pins
       this copy to it. */
    expect([...ADMISSIBLE_ANCHOR_TYPES]).toEqual([
      'application-component', 'node', 'system-software',
    ])
  })
})



describe('summariseSeverities', () => {
  it('counts by severity in canonical order, dropping empty buckets', () => {
    const out = summariseSeverities([
      { severity: 'HIGH' }, { severity: 'high' }, { severity: 'critical' }, {},
    ])
    expect(out).toEqual([
      { severity: 'critical', count: 1 },
      { severity: 'high', count: 2 },
      { severity: 'unknown', count: 1 },
    ])
  })

  it('appends non-canonical severities after the canonical ones', () => {
    const out = summariseSeverities([{ severity: 'low' }, { severity: 'moderate' }])
    expect(out).toEqual([
      { severity: 'low', count: 1 },
      { severity: 'moderate', count: 1 },
    ])
  })
})

