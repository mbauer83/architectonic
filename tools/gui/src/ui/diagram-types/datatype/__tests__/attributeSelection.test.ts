import { describe, expect, it } from 'vitest'
import {
  attributeKeyBadges,
  attributeTypeLabel,
  buildClassifierAttributes,
  toAttributeDetail,
} from '../attributeSelection'

const diagramEntities = {
  classifier: [
    {
      id: 'CLF@1.aa.artifact',
      label: 'Artifact',
      attributes: [
        { id: 'a_aid', name: 'artifact_id', type: { kind: 'primitive', name: 'String' }, role: 'Stable id' },
        { id: 'a_path', name: 'path', type: { kind: 'primitive', name: 'String' }, optional: true },
        { id: 'a_owner', name: 'owner', type: { kind: 'classifier', id: 'CLF@1.bb.person' }, multiplicity: '0..1' },
      ],
      identity: ['a_aid'],
      unique_keys: [{ name: 'path', attribute_ids: ['a_path'] }],
    },
  ],
}

describe('buildClassifierAttributes', () => {
  it('parses attributes, identity, and unique keys keyed by classifier id', () => {
    const map = buildClassifierAttributes(diagramEntities)
    const info = map.get('CLF@1.aa.artifact')
    expect(info?.label).toBe('Artifact')
    expect(info?.attributes.map((a) => a.name)).toEqual(['artifact_id', 'path', 'owner'])
    expect(info?.identity).toEqual(['a_aid'])
    expect(info?.uniqueKeys).toEqual([{ name: 'path', attribute_ids: ['a_path'] }])
  })

  it('returns an empty map for non-datatype diagram-entities', () => {
    expect(buildClassifierAttributes({ node: [] }).size).toBe(0)
    expect(buildClassifierAttributes(undefined).size).toBe(0)
  })
})

describe('attributeTypeLabel', () => {
  it('renders a primitive by its name', () => {
    expect(attributeTypeLabel({ name: 'x', type: { kind: 'primitive', name: 'String' } })).toBe('String')
  })

  it('shows the name a classifier type was picked by, not the id it is stored as', () => {
    // A classifier reference is an id on disk and a name to a reader. It rendered as the id, so an
    // attribute typed by picking `ArtifactId` from a dropdown read back as `CLF@…` — worst for a
    // repository's own primitives, whose name is the whole point of declaring one.
    const labels = new Map([['CLF@1.bb.person', 'Person']])
    expect(attributeTypeLabel({ name: 'x', type: { kind: 'classifier', id: 'CLF@1.bb.person' } }, labels))
      .toBe('Person')
  })

  it('falls back to the id for a classifier this diagram does not declare', () => {
    // Cross-diagram references resolve to nothing here; the id names the thing where an empty cell
    // would name nothing.
    const labels = new Map([['CLF@1.other.thing', 'Thing']])
    expect(attributeTypeLabel({ name: 'x', type: { kind: 'classifier', id: 'CLF@1.bb.person' } }, labels))
      .toBe('CLF@1.bb.person')
    expect(attributeTypeLabel({ name: 'x', type: { kind: 'classifier', id: 'CLF@1.bb.person' } }))
      .toBe('CLF@1.bb.person')
  })

  it('renders nothing for an attribute with no declared type', () => {
    expect(attributeTypeLabel({ name: 'x' })).toBe('')
  })
})

describe('attributeKeyBadges', () => {
  const info = buildClassifierAttributes(diagramEntities).get('CLF@1.aa.artifact')!

  it('flags identity and unique-key membership', () => {
    expect(attributeKeyBadges(info, 'a_aid')).toEqual(['identity'])
    expect(attributeKeyBadges(info, 'a_path')).toEqual(['unique: path'])
    expect(attributeKeyBadges(info, 'a_owner')).toEqual([])
  })
})

describe('toAttributeDetail', () => {
  const info = buildClassifierAttributes(diagramEntities).get('CLF@1.aa.artifact')!

  it('shapes a full detail payload with all fields', () => {
    const detail = toAttributeDetail(info, info.attributes[2], 'CLF@1.aa.artifact')
    expect(detail).toMatchObject({
      classifierId: 'CLF@1.aa.artifact',
      attributeId: info.attributes[2].id,
      name: 'owner',
      typeLabel: 'CLF@1.bb.person',
      multiplicity: '0..1',
      optional: false,
      ownerLabel: 'Artifact',
      badges: [],
    })
  })

  it('addresses the record by classifier + attribute id for a metadata patch', () => {
    const detail = toAttributeDetail(info, info.attributes[0], 'CLF@1.aa.artifact')
    expect(detail.classifierId).toBe('CLF@1.aa.artifact')
    expect(detail.attributeId).toBe(info.attributes[0].id)
  })
})
