/**
 * Tests for WU-E4: C4 model-backed edit sidebar — entity curation.
 *
 * Pure reactive-logic tests: buildC4RoleMap, parseExcludedIds, groupEntitiesByRole,
 * and the exclude-toggle logic.
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  buildC4RoleMap,
  parseExcludedIds,
  groupEntitiesByRole,
  resolveScopeEntityId,
} from '../C4DiagramEditor.helpers'
import type { DiagramOwnEntityTypeUiConfig, EntityDisplayInfo } from '../../../../domain'
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

describe('buildC4RoleMap', () => {
  it('maps ArchiMate types to C4 role info', () => {
    const map = buildC4RoleMap(SYSTEM_CONTEXT_DOTS)
    expect(map.get('business-actor')).toEqual({ label: 'Person', entityType: 'person' })
    expect(map.get('business-role')).toEqual({ label: 'Person', entityType: 'person' })
    expect(map.get('application-component')).toEqual({ label: 'Software System', entityType: 'software-system' })
  })

  it('maps own entity_type to itself', () => {
    const map = buildC4RoleMap(SYSTEM_CONTEXT_DOTS)
    expect(map.get('person')).toEqual({ label: 'Person', entityType: 'person' })
    expect(map.get('software-system')).toEqual({ label: 'Software System', entityType: 'software-system' })
  })

  it('returns empty map for empty config', () => {
    expect(buildC4RoleMap([])).toEqual(new Map())
  })

  it('does not overwrite earlier mappings with later ones', () => {
    const dots: DiagramOwnEntityTypeUiConfig[] = [
      makeDot('person', 'Person', ['shared-type']),
      makeDot('system', 'System', ['shared-type']),
    ]
    const map = buildC4RoleMap(dots)
    expect(map.get('shared-type')?.entityType).toBe('person')
  })
})

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

describe('groupEntitiesByRole', () => {
  const scope = makeEntity('SCOPE', 'application-component', 'My System')
  const person = makeEntity('P1', 'business-actor', 'Alice')
  const system = makeEntity('S1', 'application-component', 'External Billing')

  it('excludes the scope entity from groups', () => {
    const groups = groupEntitiesByRole([scope, person, system], 'SCOPE', SYSTEM_CONTEXT_DOTS)
    const allEntityIds = groups.flatMap(g => g.entities.map(e => e.artifact_id))
    expect(allEntityIds).not.toContain('SCOPE')
  })

  it('groups entities by their C4 role', () => {
    const groups = groupEntitiesByRole([scope, person, system], 'SCOPE', SYSTEM_CONTEXT_DOTS)
    const personGroup = groups.find(g => g.entityType === 'person')
    const systemGroup = groups.find(g => g.entityType === 'software-system')
    expect(personGroup?.entities.map(e => e.artifact_id)).toEqual(['P1'])
    expect(systemGroup?.entities.map(e => e.artifact_id)).toEqual(['S1'])
  })

  it('omits groups with no entities', () => {
    const groups = groupEntitiesByRole([scope, person], 'SCOPE', SYSTEM_CONTEXT_DOTS)
    expect(groups.some(g => g.entityType === 'software-system')).toBe(false)
  })

  it('places unknown ArchiMate types in an "Other" group', () => {
    const unknown = makeEntity('U1', 'assessment', 'Unknown')
    const groups = groupEntitiesByRole([scope, unknown], 'SCOPE', SYSTEM_CONTEXT_DOTS)
    const otherGroup = groups.find(g => g.entityType === '__other__')
    expect(otherGroup?.entities.map(e => e.artifact_id)).toEqual(['U1'])
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
