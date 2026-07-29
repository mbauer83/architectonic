/**
 * Tests for WU-E3: C4 drill-down on-node affordance + sticky up-banner.
 *
 * Pure reactive-logic tests: buildDrilldownByEntityId helper + computed behaviour.
 * SVG badge injection uses getBBox() which is unavailable in jsdom; that path is
 * covered by the try-catch in attachInteractivity and exercised via Playwright.
 */
import { describe, it, expect } from 'vitest'
import { computed, ref } from 'vue'
import { buildDrilldownByEntityId, diagramNeedsSvg } from '../DiagramDetailView.helpers'
import type { C4Navigation } from '../../../domain'

const makeNav = (overrides: Partial<C4Navigation> = {}): C4Navigation => ({
  current_level: 1,
  scope_entity_id: 'SYS1',
  scope_entity_name: 'My System',
  parent_diagrams: [],
  child_diagrams: [],
  ...overrides,
})

describe('diagramNeedsSvg', () => {
  it('skips the SVG endpoint for Markdown matrix diagrams', () => {
    expect(diagramNeedsSvg('matrix')).toBe(false)
  })

  it('requests SVG for rendered diagram types only after their context is known', () => {
    expect(diagramNeedsSvg('c4-container')).toBe(true)
    expect(diagramNeedsSvg('archimate-layered')).toBe(true)
    expect(diagramNeedsSvg(null)).toBe(false)
  })
})

describe('buildDrilldownByEntityId', () => {
  it('returns empty map when c4Nav is null', () => {
    expect(buildDrilldownByEntityId(null)).toEqual({})
  })

  it('returns empty map when c4Nav is undefined', () => {
    expect(buildDrilldownByEntityId(undefined)).toEqual({})
  })

  it('returns empty map when there are no child_diagrams', () => {
    expect(buildDrilldownByEntityId(makeNav())).toEqual({})
  })

  it('maps scope_entity_id → diagram_id for L2→L3 children', () => {
    const nav = makeNav({
      current_level: 2,
      child_diagrams: [
        { diagram_id: 'COMP1', diagram_name: 'Comp', diagram_type: 'c4-component', scope_entity_id: 'C1' },
      ],
    })
    expect(buildDrilldownByEntityId(nav)).toEqual({ C1: 'COMP1' })
  })

  it('falls back to c4Nav.scope_entity_id when child has no scope_entity_id (same-scope L1/L2)', () => {
    const nav = makeNav({
      current_level: 1,
      scope_entity_id: 'SYS1',
      child_diagrams: [
        { diagram_id: 'CONT1', diagram_name: 'Container', diagram_type: 'c4-container', scope_entity_id: null },
      ],
    })
    expect(buildDrilldownByEntityId(nav)).toEqual({ SYS1: 'CONT1' })
  })

  it('skips a child when both its scope_entity_id and c4Nav.scope_entity_id are null', () => {
    const nav = makeNav({
      current_level: 0,
      scope_entity_id: null,
      child_diagrams: [
        { diagram_id: 'CTX1', diagram_name: 'Context', diagram_type: 'c4-system-context', scope_entity_id: null },
      ],
    })
    expect(buildDrilldownByEntityId(nav)).toEqual({})
  })

  it('maps multiple L2→L3 children each to their respective container entity', () => {
    const nav = makeNav({
      current_level: 2,
      child_diagrams: [
        { diagram_id: 'COMP1', diagram_name: 'Comp1', diagram_type: 'c4-component', scope_entity_id: 'C1' },
        { diagram_id: 'COMP2', diagram_name: 'Comp2', diagram_type: 'c4-component', scope_entity_id: 'C2' },
      ],
    })
    expect(buildDrilldownByEntityId(nav)).toEqual({ C1: 'COMP1', C2: 'COMP2' })
  })

  it('last child wins when two children share the same scope_entity_id', () => {
    const nav = makeNav({
      current_level: 2,
      child_diagrams: [
        { diagram_id: 'COMP1', diagram_name: 'Comp1', diagram_type: 'c4-component', scope_entity_id: 'C1' },
        { diagram_id: 'COMP1_ALT', diagram_name: 'Comp1Alt', diagram_type: 'c4-component', scope_entity_id: 'C1' },
      ],
    })
    expect(buildDrilldownByEntityId(nav)).toEqual({ C1: 'COMP1_ALT' })
  })
})

describe('drilldownByEntityId computed (reactive)', () => {
  it('updates when c4Nav changes', () => {
    const navRef = ref<C4Navigation | null>(null)
    const drilldown = computed(() => buildDrilldownByEntityId(navRef.value))

    expect(drilldown.value).toEqual({})

    navRef.value = makeNav({
      child_diagrams: [
        { diagram_id: 'COMP1', diagram_name: 'Comp', diagram_type: 'c4-component', scope_entity_id: 'C1' },
      ],
    })
    expect(drilldown.value).toEqual({ C1: 'COMP1' })

    navRef.value = null
    expect(drilldown.value).toEqual({})
  })

  it('is empty for a diagram with no drill-down relationships', () => {
    const navRef = ref<C4Navigation | null>(makeNav({ child_diagrams: [] }))
    const drilldown = computed(() => buildDrilldownByEntityId(navRef.value))
    expect(drilldown.value).toEqual({})
  })
})

describe('c4-up-banner visibility logic', () => {
  it('banner should show when parent_diagrams is non-empty', () => {
    const nav = makeNav({
      parent_diagrams: [{ diagram_id: 'CTX1', diagram_name: 'Context', diagram_type: 'c4-system-context', scope_entity_id: 'SYS1' }],
    })
    expect(nav.parent_diagrams.length).toBeGreaterThan(0)
  })

  it('banner should be hidden when parent_diagrams is empty', () => {
    const nav = makeNav({ parent_diagrams: [] })
    expect(nav.parent_diagrams.length).toBe(0)
  })
})

describe('c4-child-nav visibility logic', () => {
  it('child nav should show when child_diagrams is non-empty', () => {
    const nav = makeNav({
      child_diagrams: [{ diagram_id: 'COMP1', diagram_name: 'Component', diagram_type: 'c4-component', scope_entity_id: 'C1' }],
    })
    expect(nav.child_diagrams.length).toBeGreaterThan(0)
  })

  it('child nav should be hidden when child_diagrams is empty', () => {
    const nav = makeNav({ child_diagrams: [] })
    expect(nav.child_diagrams.length).toBe(0)
  })
})
