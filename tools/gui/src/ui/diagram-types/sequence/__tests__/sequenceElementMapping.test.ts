/**
 * Tests for the sequence viewer extension's `mapElements`. The fake SVG trees below mirror,
 * element-for-element, `fixtures/charge-flow.svg` — a real render (PlantUML 1.2026.3, via
 * `plantuml.jar`) of a diagram with one bound lifeline (`entity_id: APC@1.orders`, alias
 * `App_Orders`) and one unbound lifeline (local id `ll-anon1`, alias `ll_anon1` — the renderer's
 * `normalize_puml_alias` of its own local id), plus two messages. Regenerate the fixture with
 * `src/diagram_types/sequence/renderer.py`'s `SequencePumlRenderer` + `plantuml.jar -tsvg` if the
 * renderer's emitted SVG conventions ever change.
 */
import { describe, it, expect } from 'vitest'
import { sequenceMapElements } from '../sequenceElementMapping'
import { FakeElement, FakeSvgRoot, asSvgRoot, makeEntity } from '../../../lib/__tests__/svgDomFakes'

/** Builds the fake tree for one PlantUML participant (lifeline + head + tail groups). */
function addParticipant(root: FakeSvgRoot, qualifiedName: string): FakeElement[] {
  const groups = ['participant-lifeline', 'participant participant-head', 'participant participant-tail'].map((cls) => {
    const g = root.appendChild(new FakeElement('g'))
    g.setAttribute('class', cls)
    g.setAttribute('data-qualified-name', qualifiedName)
    return g
  })
  return groups
}

/** Builds the fake tree for one PlantUML message arrow (no id/attribute ties back to our data). */
function addMessage(root: FakeSvgRoot): FakeElement {
  const g = root.appendChild(new FakeElement('g'))
  g.setAttribute('class', 'message')
  return g
}

const diagramEntities = (): Record<string, unknown> => ({
  lifeline: [
    { id: 'll1', label: 'Orders Service', entity_id: 'APC@1.orders' },
    { id: 'll-anon1', label: 'Anonymous Caller' },
  ],
  message: [
    { id: 'm1', label: 'charge' },
    { id: 'm2', label: 'ack', arrow: 'reply' },
  ],
  _connections: [
    { id: 'c1', conn_type: 'seq-from', source: 'm1', target: 'll1' },
    { id: 'c2', conn_type: 'seq-to', source: 'm1', target: 'll-anon1' },
    { id: 'c3', conn_type: 'seq-from', source: 'm2', target: 'll-anon1' },
    { id: 'c4', conn_type: 'seq-to', source: 'm2', target: 'll1' },
  ],
})

describe('sequenceMapElements', () => {
  it('maps a bound lifeline (head+tail+lifeline groups) to the real model entity it represents', () => {
    const root = new FakeSvgRoot()
    const orderGroups = addParticipant(root, 'App_Orders')
    addParticipant(root, 'll_anon1')

    // A bound lifeline's alias is the real entity's display_alias, so it resolves to the real
    // entity's own artifact id (not a diagram-local `#lifeline/...` placeholder) — the same
    // entity `repo.list_entities()` contributes to the diagram context per `_diagram_context.py`.
    const { nodes } = sequenceMapElements(asSvgRoot(root), {
      entities: [makeEntity('APC@1.orders', 'App_Orders', 'application-component')],
      connections: [],
      diagramEntities: diagramEntities(),
    })
    expect(nodes.get('APC@1.orders')).toEqual(orderGroups)
  })

  it('maps an unbound lifeline via its own normalized local id, not a positional alias', () => {
    const root = new FakeSvgRoot()
    addParticipant(root, 'App_Orders')
    const anonGroups = addParticipant(root, 'll_anon1')

    const { nodes } = sequenceMapElements(asSvgRoot(root), {
      entities: [makeEntity('SEQ@1#lifeline/ll-anon1', 'll-anon1', 'lifeline')],
      connections: [],
      diagramEntities: diagramEntities(),
    })
    expect(nodes.get('SEQ@1#lifeline/ll-anon1')).toEqual(anonGroups)
  })

  it('maps message arrows to message entities by DOM order', () => {
    const root = new FakeSvgRoot()
    addParticipant(root, 'App_Orders')
    addParticipant(root, 'll_anon1')
    const msg1 = addMessage(root)
    const msg2 = addMessage(root)

    const { nodes } = sequenceMapElements(asSvgRoot(root), {
      entities: [
        makeEntity('SEQ@1#message/m1', 'm1', 'message'),
        makeEntity('SEQ@1#message/m2', 'm2', 'message'),
      ],
      connections: [],
      diagramEntities: diagramEntities(),
    })
    expect(nodes.get('SEQ@1#message/m1')).toEqual([msg1])
    expect(nodes.get('SEQ@1#message/m2')).toEqual([msg2])
  })

  it('skips a message with no complete seq-from/seq-to pair so DOM order stays aligned', () => {
    const root = new FakeSvgRoot()
    // Renderer emits no <g class="message"> for an incomplete message — only one arrow here.
    const onlyArrow = addMessage(root)

    const entities = diagramEntities()
    ;(entities.message as Array<Record<string, unknown>>).unshift({ id: 'm0', label: 'incomplete' })

    const { nodes } = sequenceMapElements(asSvgRoot(root), {
      entities: [makeEntity('SEQ@1#message/m1', 'm1', 'message')],
      connections: [],
      diagramEntities: entities,
    })
    expect(nodes.get('SEQ@1#message/m1')).toEqual([onlyArrow])
  })

  it('returns no message mapping when diagramEntities is not supplied', () => {
    const root = new FakeSvgRoot()
    addMessage(root)
    const { nodes } = sequenceMapElements(asSvgRoot(root), { entities: [], connections: [] })
    expect(nodes.size).toBe(0)
  })
})
