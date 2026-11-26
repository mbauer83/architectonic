import { describe, expect, it } from 'vitest'
import { SHAPE_DRAWING } from '../layout/__tests__/canvasDrawingFixtures'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import { composedOver, drawnCommands, type ComposedView, type DrawnContent } from './candidateDrawing'

const SERVICE = 'SRV@1712870400.Uv9Wx9.repository-promotion-service'
const ARTIFACTS = 'PRC@1712870400.0Rz5Ex.promote-artifacts'
const ACTOR = 'ACT@1712870400.Nn7Oo7.architect'
const QUEUE = 'DOB@1795000000.Queue01.promotion-queue'
const entity = (id: string, name: string, extra: Record<string, unknown> = {}) =>
  ({ id, fields: { name, artifact_type: 'application-service', group: 'core', ...extra } })
const relation = (source: string, type: string, target: string) =>
  ({ source_entity: source, connection_type: type, target_entity: target, fields: { description: '' } })

const drawn: DrawnContent = {
  entities: [
    { artifact_id: SERVICE, name: 'Repository Promotion Service' },
    { artifact_id: ARTIFACTS, name: 'Promote Artifacts' },
    { artifact_id: ACTOR, name: 'Architect' },
  ],
  connections: [{ artifact_id: `${ARTIFACTS}---${SERVICE}@@archimate-serving` }],
  undrawn: [{ artifact_id: `${ACTOR}---${SERVICE}@@archimate-association` }],
}

describe('a candidate drawn over its picture', () => {
  it('draws nothing anew where it changes nothing the picture shows', () => {
    const view: ComposedView = {
      entities: [entity(SERVICE, 'Repository Promotion Service'), entity(ARTIFACTS, 'Promote Artifacts')],
      connections: [relation(ARTIFACTS, 'archimate-serving', SERVICE)],
    }
    expect(drawnCommands(view, drawn)).toEqual([])
  })

  it('renames what it renames, creates what it creates, and links what it links', () => {
    const view: ComposedView = {
      entities: [
        entity(SERVICE, 'Promotion Review Service'),
        { ...entity('DOB@1795000000.Queue01', 'Promotion queue', { artifact_type: 'data-object' }), artifact_id: QUEUE },
      ],
      connections: [relation(SERVICE, 'archimate-access', 'DOB@1795000000.Queue01')],
    }
    expect(drawnCommands(view, drawn)).toEqual([
      { op: 'model.element.create', artifact_id: QUEUE, artifact_type: 'data-object', name: 'Promotion queue', group: 'core' },
      { op: 'model.element.rename', artifact_id: SERVICE, name: 'Promotion Review Service' },
      {
        op: 'model.relation.create', artifact_id: `${SERVICE}---${QUEUE}@@archimate-access`, description: '',
        src_multiplicity: '', tgt_multiplicity: '',
      },
    ])
  })

  it('links a created element to one its operations name by the short id, as the picture draws that one', () => {
    const view: ComposedView = {
      entities: [{ ...entity('DOB@1795000000.Queue01', 'Promotion queue', { artifact_type: 'data-object' }), artifact_id: QUEUE }],
      connections: [relation('DOB@1795000000.Queue01', 'archimate-serving', 'SRV@1712870400.Uv9Wx9')],
    }
    expect(drawnCommands(view, drawn).filter((one) => one.op === 'model.relation.create')).toEqual([{
      op: 'model.relation.create', artifact_id: `${QUEUE}---${SERVICE}@@archimate-serving`, description: '',
      src_multiplicity: '', tgt_multiplicity: '',
    }])
  })

  it('leaves a relation the model holds undrawn as it is, and one to an element not drawn', () => {
    const view: ComposedView = {
      entities: [entity(SERVICE, 'Repository Promotion Service'), entity(ACTOR, 'Architect')],
      connections: [
        relation(ACTOR, 'archimate-association', SERVICE),
        relation(ACTOR, 'archimate-assignment', 'ROL@1776633082.udXPfB.author'),
      ],
    }
    expect(drawnCommands(view, drawn)).toEqual([])
  })

  it('keeps what it removes on the picture, for the reader to mark as a ghost', () => {
    const view: ComposedView = { entities: [entity(SERVICE, 'Repository Promotion Service')], connections: [] }
    expect(drawnCommands(view, drawn)).toEqual([])
  })
})

describe('what a candidate is composed over', () => {
  const typeBox = {
    alias: 'T', kind: 'type' as const, section: 'boxes' as const, label: 'Application Components',
    rule: { type: 'application-component' }, extent: { left: 0, top: 0, right: 10, bottom: 10 }, words: [],
    drawing: SHAPE_DRAWING,
  }
  const view: LayoutGeometry = {
    artifact_id: '', name: 'Scope', canvas: { left: 0, top: 0, right: 10, bottom: 10 }, backdrop: [],
    surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] }, elements: [], boxes: [typeBox],
    relations: [],
  }
  const start = (artifactId: string) => ({
    artifact_id: artifactId, name: 'Scope', diagram_type: 'archimate-layered', entity_ids_used: [SERVICE],
  })

  it('states the boxes a generated view is drawn with as its own, so a relation added does not unbox them', () => {
    expect(composedOver(start(''), view)?.authored_groupings).toEqual([
      { label: 'Application Components', 'entity-ids': [], rule: { type: 'application-component' } },
    ])
  })

  it('composes over a stored diagram as it states itself, and over a view not yet drawn as it is', () => {
    expect(composedOver(start('ARC@1.a.diagram'), view)?.authored_groupings).toBeUndefined()
    expect(composedOver(start(''), null)?.authored_groupings).toBeUndefined()
    expect(composedOver(null, view)).toBeNull()
  })
})
