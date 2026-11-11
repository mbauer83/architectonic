/**
 * Tests for WU-E4: C4 model-backed edit sidebar — entity curation.
 *
 * Pure reactive-logic tests: parseExcludedIds, groupEntitiesByDrawnType,
 * and the exclude-toggle logic.
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  parseExcludedIds,
  groupEntitiesByDrawnType,
  resolveScopeEntityId,
  UNCLASSIFIED,
} from '../C4DiagramEditor.helpers'
import type { DerivedEntity, DiagramOwnEntityTypeUiConfig, EntityDisplayInfo } from '../../../../domain'
import type { EntityTypeName } from '../../../../domain/types.generated'

const makeDot = (
  entityType: string,
  label: string,
  archimateTypes: string[],
): DiagramOwnEntityTypeUiConfig => ({
  entity_type: entityType,
  label,
  plural: label + 's',
  min: 0,
  max: null,
  mapping_required: false,
  permitted_mappings: { entity_types: archimateTypes, entity_classes: [], sources: [] },
  properties: [],
  // The eight fields the schema used to omit. `identity_scope` and `permitted_connections` are the
  // ones that govern authoring, and a config decoded without them looked complete.
  classes: [],
  create_when: '',
  never_create_when: '',
  permitted_connections: [],
  required_connections: [],
  managed_fields: null,
  identity_scope: 'diagram',
  id_prefix: null,
  include_in_global_search: false,
  editable_metadata: { entity: [], subparts: {} },
})

const makeEntity = (id: string, archType: EntityTypeName, name = id): EntityDisplayInfo => ({
  artifact_id: id,
  name,
  artifact_type: archType,
  domain: 'application',
  subdomain: '',
  status: 'active',
  display_alias: '',
  element_type: archType,
  element_label: name,
  diagram_internal: false,
})

const SYSTEM_CONTEXT_DOTS: DiagramOwnEntityTypeUiConfig[] = [
  makeDot('person', 'Person', ['business-actor', 'business-role']),
  makeDot('software-system', 'Software System', ['application-component', 'application-service']),
]

describe('parseExcludedIds', () => {
  it('returns empty set when field is absent', () => {
    expect(parseExcludedIds({})).toEqual(new Set())
  })

  it('returns empty set when field is not an array', () => {
    expect(parseExcludedIds({ _excluded_entity_ids: 'not-array' })).toEqual(new Set())
  })

  it('parses string array into a Set', () => {
    const result = parseExcludedIds({ _excluded_entity_ids: ['A', 'B'] })
    expect(result).toEqual(new Set(['A', 'B']))
  })

  it('filters out non-string entries', () => {
    const result = parseExcludedIds({ _excluded_entity_ids: ['A', 42, null, 'B'] })
    expect(result).toEqual(new Set(['A', 'B']))
  })
})

describe('groupEntitiesByDrawnType', () => {
  const scope = makeEntity('SCOPE', 'application-component', 'My System')
  const person = makeEntity('P1', 'business-actor', 'Alice')
  const system = makeEntity('S1', 'application-component', 'External Billing')
  const part = makeEntity('C1', 'application-component', 'Write Path')
  const COMPONENT_DOTS = [...SYSTEM_CONTEXT_DOTS, makeDot('component', 'Component', ['application-component'])]
  const row = (id: string, itemType: string): DerivedEntity =>
    ({ id, name: id, item_type: itemType, role: 'internal', excluded: false })

  it('excludes the scope entity from groups', () => {
    const groups = groupEntitiesByDrawnType([scope, person, system], 'SCOPE', SYSTEM_CONTEXT_DOTS, [])
    const allEntityIds = groups.flatMap(g => g.entities.map(e => e.artifact_id))
    expect(allEntityIds).not.toContain('SCOPE')
  })

  it('groups each entity under the type the server draws it as', () => {
    const derived = [row('P1', 'person'), row('S1', 'software-system')]
    const groups = groupEntitiesByDrawnType([scope, person, system], 'SCOPE', SYSTEM_CONTEXT_DOTS, derived)
    expect(groups.find(g => g.entityType === 'person')?.entities.map(e => e.artifact_id)).toEqual(['P1'])
    expect(groups.find(g => g.entityType === 'software-system')?.entities.map(e => e.artifact_id)).toEqual(['S1'])
  })

  it('puts an application component the projection draws as a component under Components (B80)', () => {
    // The type table permits an application component as a software system first; reading it put every
    // component of a component diagram under "Software Systems" while the picture drew «component».
    const groups = groupEntitiesByDrawnType([scope, part], 'SCOPE', COMPONENT_DOTS, [row('C1', 'component')])
    expect(groups.map(g => [g.label, g.entities.map(e => e.artifact_id)])).toEqual([['Components', ['C1']]])
  })

  it('omits groups with no entities', () => {
    const groups = groupEntitiesByDrawnType([scope, person], 'SCOPE', SYSTEM_CONTEXT_DOTS, [row('P1', 'person')])
    expect(groups.some(g => g.entityType === 'software-system')).toBe(false)
  })

  it('places an entity the server drew as no declared type, or did not classify, under "Other"', () => {
    const unknown = makeEntity('U1', 'assessment', 'Unknown')
    const groups = groupEntitiesByDrawnType([scope, unknown, person], 'SCOPE', SYSTEM_CONTEXT_DOTS, [row('U1', 'gizmo')])
    expect(groups.find(g => g.entityType === '__other__')?.entities.map(e => e.artifact_id)).toEqual(['U1', 'P1'])
  })

  it('lists everything as unclassified until the server has said', () => {
    const groups = groupEntitiesByDrawnType([scope, person, system], 'SCOPE', SYSTEM_CONTEXT_DOTS, null)
    expect(groups.map(g => [g.entityType, g.label])).toEqual([[UNCLASSIFIED, 'Entities']])
  })
})

// ── resolveScopeEntityId — T17 data path ─────────────────────────────────────

describe('resolveScopeEntityId', () => {
  it('returns _scope_entity_id from diagram_entities (model-backed C4 with binding-injected id)', () => {
    const de = { _scope_entity_id: 'APP@1780783671.hkrdtm.architecture-management-platform' }
    expect(resolveScopeEntityId(de)).toBe('APP@1780783671.hkrdtm.architecture-management-platform')
  })

  it('falls back to inline scope item entity_id (standalone mode after scope selection)', () => {
    const de = {
      'software-system': [
        { id: '_scope', entity_id: 'APP@inline-scope', label: 'My System', scope: true },
      ],
    }
    expect(resolveScopeEntityId(de)).toBe('APP@inline-scope')
  })

  it('returns empty string when diagram_entities is empty (no scope set)', () => {
    expect(resolveScopeEntityId({})).toBe('')
  })

  it('returns empty string when _scope_entity_id is an empty string', () => {
    expect(resolveScopeEntityId({ _scope_entity_id: '' })).toBe('')
  })

  it('ignores private underscore keys when looking for inline scope', () => {
    const de = { _excluded_entity_ids: [{ scope: true, entity_id: 'SHOULD-NOT-MATCH' }] }
    expect(resolveScopeEntityId(de)).toBe('')
  })
})

describe('exclude toggle logic', () => {
  it('adding an entity to excluded set emits updated ids', () => {
    const excluded = ref(new Set<string>())
    const emitted: string[][] = []
    const toggleExclude = (id: string) => {
      const next = new Set(excluded.value)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      excluded.value = next
      emitted.push([...next])
    }
    toggleExclude('E1')
    expect(excluded.value.has('E1')).toBe(true)
    expect(emitted[0]).toEqual(['E1'])
  })

  it('restoring an excluded entity removes it from the set', () => {
    const excluded = ref(new Set<string>(['E1', 'E2']))
    const emitted: string[][] = []
    const toggleExclude = (id: string) => {
      const next = new Set(excluded.value)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      excluded.value = next
      emitted.push([...next])
    }
    toggleExclude('E1')
    expect(excluded.value.has('E1')).toBe(false)
    expect(excluded.value.has('E2')).toBe(true)
  })
})
