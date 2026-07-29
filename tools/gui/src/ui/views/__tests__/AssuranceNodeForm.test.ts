/**
 * Pure logic tests for AssuranceNodeForm helpers.
 *
 * Tests field-visibility predicates, safety-disposition safeguard, canSubmit guard,
 * and field-reset helper without mounting the component.
 * Follows the same pattern as adHocTypeRoundtrip.test.ts and DiagramDetailView.diagramOnly.test.ts.
 */
import { describe, it, expect } from 'vitest'
import {
  showConcernClass,
  showDisposition,
  showUcaType,
  showBindingStatus,
  showNodeRole,
  showSafeguardWarning,
  canSubmit,
  resetTypeSpecificFields,
} from '../AssuranceNodeForm.helpers'

// ── canSubmit guard ──────────────────────────────────────────────────────────

describe('canSubmit', () => {
  it('returns false when name is empty', () => {
    expect(canSubmit('loss', '', false)).toBe(false)
  })

  it('returns false when node_type is empty', () => {
    expect(canSubmit('', 'Loss 1', false)).toBe(false)
  })

  it('returns false when loading', () => {
    expect(canSubmit('loss', 'Loss 1', true)).toBe(false)
  })

  it('returns true with type + name + not loading', () => {
    expect(canSubmit('loss', 'Loss 1', false)).toBe(true)
  })

  it('trims whitespace for the guard', () => {
    expect(canSubmit('  ', 'Loss 1', false)).toBe(false)
    expect(canSubmit('loss', '   ', false)).toBe(false)
  })
})

// ── Field visibility by node type ────────────────────────────────────────────

describe('showConcernClass', () => {
  it('true for assurance-constraint', () => expect(showConcernClass('assurance-constraint')).toBe(true))
  it('true for risk', () => expect(showConcernClass('risk')).toBe(true))
  it('true for hazard', () => expect(showConcernClass('hazard')).toBe(true))
  it('true for obligation', () => expect(showConcernClass('obligation')).toBe(true))
  it('false for loss', () => expect(showConcernClass('loss')).toBe(false))
  it('false for incident', () => expect(showConcernClass('incident')).toBe(false))
})

describe('showDisposition', () => {
  it('true only for assurance-constraint', () => expect(showDisposition('assurance-constraint')).toBe(true))
  it('false for risk', () => expect(showDisposition('risk')).toBe(false))
  it('false for hazard', () => expect(showDisposition('hazard')).toBe(false))
})

describe('showUcaType', () => {
  it('true only for unsafe-control-action', () => expect(showUcaType('unsafe-control-action')).toBe(true))
  it('false for hazard', () => expect(showUcaType('hazard')).toBe(false))
  it('false for loss', () => expect(showUcaType('loss')).toBe(false))
})

describe('showBindingStatus + showNodeRole', () => {
  it('both true for control-structure-node', () => {
    expect(showBindingStatus('control-structure-node')).toBe(true)
    expect(showNodeRole('control-structure-node')).toBe(true)
  })
  it('both false for other types', () => {
    expect(showBindingStatus('loss')).toBe(false)
    expect(showNodeRole('loss')).toBe(false)
  })
})

// ── Safety-disposition safeguard (E503) ──────────────────────────────────────

describe('showSafeguardWarning', () => {
  it('true for accepted + safety + assurance-constraint', () => {
    expect(showSafeguardWarning('assurance-constraint', 'accepted', 'safety')).toBe(true)
  })

  it('true for accepted + security + assurance-constraint', () => {
    expect(showSafeguardWarning('assurance-constraint', 'accepted', 'security')).toBe(true)
  })

  it('false for alarp-justified + safety', () => {
    expect(showSafeguardWarning('assurance-constraint', 'alarp-justified', 'safety')).toBe(false)
  })

  it('false for accepted + financial (non-safety class)', () => {
    expect(showSafeguardWarning('assurance-constraint', 'accepted', 'financial')).toBe(false)
  })

  it('false when node_type is not assurance-constraint (disposition not shown)', () => {
    expect(showSafeguardWarning('risk', 'accepted', 'safety')).toBe(false)
  })

  it('false when disposition is empty', () => {
    expect(showSafeguardWarning('assurance-constraint', '', 'safety')).toBe(false)
  })
})

// ── resetTypeSpecificFields ──────────────────────────────────────────────────

describe('resetTypeSpecificFields', () => {
  it('clears all type-specific fields, keeps others intact', () => {
    const form = {
      node_type: 'assurance-constraint',
      name: 'SC-1',
      status: 'active',
      tlp: 'TLP:AMBER',
      concern_class: 'safety',
      disposition: 'accepted',
      uca_type: 'commission',
      binding_status: 'bound',
      node_role: 'controller',
      content_text: 'some notes',
    }
    const reset = resetTypeSpecificFields(form)
    expect(reset.concern_class).toBe('')
    expect(reset.disposition).toBe('')
    expect(reset.uca_type).toBe('')
    expect(reset.binding_status).toBe('')
    expect(reset.node_role).toBe('')
    // Non-type-specific fields preserved
    expect(reset.name).toBe('SC-1')
    expect(reset.status).toBe('active')
    expect(reset.tlp).toBe('TLP:AMBER')
    expect(reset.content_text).toBe('some notes')
  })
})
