/**
 * Tests for the pure helpers exported from EntityPickerInput.vue that govern
 * fixed-level display and widen-constraint behaviour (WU-D2, strategy A).
 *
 * No DOM or component mounting needed — logic tests only.
 */
import { describe, it, expect } from 'vitest'
import {
  calcHasStageUI,
  calcCanGoBack,
  calcCanGoForward,
  dividerIndex,
  entityDisplayInfoToHit,
} from '../EntityPickerInput.helpers'
import type { EntityDisplayInfo } from '../../../domain'

// ── calcHasStageUI ─────────────────────────────────────────────────────────────

describe('calcHasStageUI', () => {
  it('returns true when nothing is fixed', () => {
    expect(calcHasStageUI(undefined, undefined, undefined)).toBe(true)
  })

  it('returns true when only domains are fixed (types selectable)', () => {
    expect(calcHasStageUI(['Application'], undefined, undefined)).toBe(true)
  })

  it('returns true when only types are fixed (domains selectable)', () => {
    expect(calcHasStageUI(undefined, ['application-component'], undefined)).toBe(true)
  })

  it('returns false when both domains and types are fixed', () => {
    expect(calcHasStageUI(['Application'], ['application-component'], undefined)).toBe(false)
  })

  it('returns false for widenableTo=none regardless of fixed state', () => {
    expect(calcHasStageUI(undefined, undefined, 'none')).toBe(false)
    expect(calcHasStageUI(['Application'], undefined, 'none')).toBe(false)
    expect(calcHasStageUI(undefined, ['application-component'], 'none')).toBe(false)
    expect(calcHasStageUI(['Application'], ['application-component'], 'none')).toBe(false)
  })

  it('returns true for widenableTo=domain when types are not fixed', () => {
    expect(calcHasStageUI(['Application'], undefined, 'domain')).toBe(true)
  })

  it('returns false for widenableTo=domain when both are fixed', () => {
    expect(calcHasStageUI(['Application'], ['application-component'], 'domain')).toBe(false)
  })
})

// ── calcCanGoBack ──────────────────────────────────────────────────────────────

describe('calcCanGoBack', () => {
  it('returns true when at entity-type stage with no fixed domains and no widenableTo', () => {
    expect(calcCanGoBack('entity-type', undefined, undefined)).toBe(true)
    expect(calcCanGoBack('entity-type', [], undefined)).toBe(true)
  })

  it('returns false when at scope stage (cannot go back from scope)', () => {
    expect(calcCanGoBack('scope', undefined, undefined)).toBe(false)
  })

  it('returns false when domains are fixed (pinned single domain → no widen)', () => {
    expect(calcCanGoBack('entity-type', ['Application'], undefined)).toBe(false)
  })

  it('returns false when domains are fixed (pinned set → no widen)', () => {
    expect(calcCanGoBack('entity-type', ['Application', 'Business'], undefined)).toBe(false)
  })

  it('returns false for widenableTo=none regardless of stage', () => {
    expect(calcCanGoBack('entity-type', undefined, 'none')).toBe(false)
    expect(calcCanGoBack('entity-type', [], 'none')).toBe(false)
  })

  it('returns true for widenableTo=domain when no domains are fixed', () => {
    expect(calcCanGoBack('entity-type', [], 'domain')).toBe(true)
  })
})

// ── calcCanGoForward ───────────────────────────────────────────────────────────

describe('calcCanGoForward', () => {
  it('returns true when at scope stage with no fixed types and no widenableTo', () => {
    expect(calcCanGoForward('scope', undefined, undefined)).toBe(true)
    expect(calcCanGoForward('scope', [], undefined)).toBe(true)
  })

  it('returns false when at entity-type stage', () => {
    expect(calcCanGoForward('entity-type', undefined, undefined)).toBe(false)
  })

  it('returns false when entity types are fixed', () => {
    expect(calcCanGoForward('scope', ['application-component'], undefined)).toBe(false)
  })

  it('returns false for widenableTo=none', () => {
    expect(calcCanGoForward('scope', undefined, 'none')).toBe(false)
    expect(calcCanGoForward('scope', [], 'none')).toBe(false)
  })

  it('returns true for widenableTo=domain when no types are fixed', () => {
    expect(calcCanGoForward('scope', [], 'domain')).toBe(true)
  })

  it('forbidden types never offered: fixedEntityTypes constrains availableEntityTypes (covered by D1)', () => {
    // The intersectWithFixed helper (tested in useEntityFilters.helpers.test.ts)
    // ensures fixedEntityTypes are the only types offered. calcCanGoForward
    // returning false when types are fixed prevents the stage from being navigable.
    expect(calcCanGoForward('scope', ['application-component', 'application-service'], undefined)).toBe(false)
  })
})

// ── entityDisplayInfoToHit ─────────────────────────────────────────────────────

describe('entityDisplayInfoToHit', () => {
  const entity: EntityDisplayInfo = {
    artifact_id: 'APP@1.Foo.bar',
    name: 'Bar',
    artifact_type: 'application-component',
    domain: 'application',
    subdomain: '',
    status: 'active',
    display_alias: 'bar',
    element_type: 'ApplicationComponent',
    element_label: 'Bar',
    diagram_internal: false,
  }

  it('adapts an entity-display item to a record_type=entity result hit', () => {
    expect(entityDisplayInfoToHit(entity)).toEqual({
      artifact_id: 'APP@1.Foo.bar',
      record_type: 'entity',
      name: 'Bar',
      status: 'active',
      path: '',
      artifact_type: 'application-component',
      domain: 'application',
      diagram_internal: false,
    })
  })
})

// ── dividerIndex ───────────────────────────────────────────────────────────────

describe('dividerIndex', () => {
  const hit = (id: string, internal: boolean) => ({
    artifact_id: id, record_type: 'entity' as const, name: id, status: 'active',
    path: '', artifact_type: 'application-component', domain: 'application',
    diagram_internal: internal,
  })

  it('is the first diagram-internal hit, -1 when all are model entities', () => {
    expect(dividerIndex([hit('a', false), hit('b', false)])).toBe(-1)
    expect(dividerIndex([hit('a', false), hit('b', true), hit('c', true)])).toBe(1)
    expect(dividerIndex([])).toBe(-1)
  })
})
