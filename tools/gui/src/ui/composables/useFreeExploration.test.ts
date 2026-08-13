import { Effect } from 'effect'
import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useForceGraph } from './useForceGraph'
import { useFreeExploration } from './useFreeExploration'

/**
 * The drawn edges are the model's edges among the drawn nodes.
 *
 * Free exploration used to ask each node for its own connections and add exactly those, so an
 * edge between two neighbours — incident to neither the root nor any node expanded so far — was
 * never in any response. Nothing filtered it out; it was never asked for. Two people looking at
 * the same set of nodes therefore saw different graphs, decided by the order they clicked in.
 *
 * The fixture is the smallest shape that can tell the two apart: a root whose two neighbours are
 * also connected to each other. A fixture without that edge passes against the defect.
 */

const ROOT = 'REQ@1.a.root'
const LEFT = 'REQ@2.b.left'
const RIGHT = 'REQ@3.c.right'
const OUTSIDE = 'REQ@4.d.outside'

/** Every edge in the little model, as `[source, target]`. */
const MODEL: ReadonlyArray<readonly [string, string]> = [
  [ROOT, LEFT],
  [ROOT, RIGHT],
  [LEFT, RIGHT],
  [RIGHT, OUTSIDE],
]

const connection = ([source, target]: readonly [string, string]) => ({
  artifact_id: `${source}---${target}@@archimate-association`,
  source,
  target,
  conn_type: 'archimate-association',
  version: '0.1.0',
  status: 'active',
  path: '',
  content_text: '',
  associated_entities: [],
  src_multiplicity: '',
  tgt_multiplicity: '',
  specializations: [],
  metadata: {},
  source_name: source,
  target_name: target,
})

/** Enough of `ModelService` for exploration, answering from `MODEL`. */
function fakeService() {
  const asked: string[][] = []
  return {
    asked,
    svc: {
      getEntity: (id: string) =>
        Effect.succeed({
          artifact_id: id, name: id, domain: 'motivation', artifact_type: 'requirement',
          conn_in: 0, conn_sym: 0, conn_out: 0,
        }),
      getConnections: (entityId: string) =>
        Effect.succeed(
          MODEL.filter(([s, t]) => s === entityId || t === entityId).map(connection),
        ),
      getConnectionsAmong: (entityIds: readonly string[]) => {
        asked.push([...entityIds])
        const inSet = new Set(entityIds)
        return Effect.succeed(MODEL.filter(([s, t]) => inSet.has(s) && inSet.has(t)).map(connection))
      },
    },
  }
}

function explorer(rootId: string) {
  const graph = useForceGraph(() => 1200, () => 800)
  const { svc, asked } = fakeService()
  const exploration = useFreeExploration({
    // The fake answers the three reads exploration makes; the rest of `ModelService` is not
    // reachable from here, and a full stub would assert nothing while going stale.
    svc: svc as never,
    nodes: graph.nodes,
    edges: graph.edges as never,
    rootId: ref(rootId),
    addNode: graph.addNode,
    addEdge: graph.addEdge,
    markExpanded: graph.markExpanded,
    spreadAroundParent: graph.spreadAroundParent,
    relayout: () => {},
    isAggregateNodeId: (id: string) => id.startsWith('agg:'),
    selectNode: () => {},
  })
  return { graph, exploration, asked }
}

/** The drawn edges as `source→target` pairs, order-independent. */
const drawn = (graph: ReturnType<typeof useForceGraph>): Set<string> =>
  new Set(graph.edges.value.map((e) => `${e.source}→${e.target}`))

/** Exploration publishes from promise callbacks; let them run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('the first hop draws every relation among the nodes it shows', () => {
  it('draws the edge between two neighbours, which no star query names', async () => {
    const { graph, exploration } = explorer(ROOT)

    exploration.loadRoot()
    await settle()

    expect(drawn(graph)).toEqual(new Set([
      `${ROOT}→${LEFT}`, `${ROOT}→${RIGHT}`, `${LEFT}→${RIGHT}`,
    ]))
  })

  it('leaves out a relation to an entity it is not showing', async () => {
    const { graph, exploration } = explorer(ROOT)

    exploration.loadRoot()
    await settle()

    expect(graph.nodes.value.map((n) => n.id)).not.toContain(OUTSIDE)
    expect(drawn(graph)).not.toContain(`${RIGHT}→${OUTSIDE}`)
  })

  it('asks about the nodes it is going to draw, not about one node at a time', async () => {
    const { exploration, asked } = explorer(ROOT)

    exploration.loadRoot()
    await settle()

    expect(asked).toEqual([[ROOT, LEFT, RIGHT]])
  })

  it('never asks about an aggregate, which stands for a group rather than being an entity', async () => {
    const { graph, exploration, asked } = explorer(ROOT)
    graph.addNode({ id: 'agg:motivation', label: 'Motivation', type: 'AGG' })

    exploration.loadRoot()
    await settle()

    expect(asked.flat()).not.toContain('agg:motivation')
  })
})

describe('the same nodes give the same graph however they were reached', () => {
  it('expanding a neighbour adds what that neighbour reaches, and no more', async () => {
    const { graph, exploration } = explorer(ROOT)
    exploration.loadRoot()
    await settle()

    exploration.expandNode(RIGHT)
    await settle()

    expect(drawn(graph)).toEqual(new Set([
      `${ROOT}→${LEFT}`, `${ROOT}→${RIGHT}`, `${LEFT}→${RIGHT}`, `${RIGHT}→${OUTSIDE}`,
    ]))
  })

  it('reaching the same population by a different route draws the same edges', async () => {
    const viaRight = explorer(ROOT)
    viaRight.exploration.loadRoot()
    await settle()
    viaRight.exploration.expandNode(RIGHT)
    await settle()

    const viaOutside = explorer(OUTSIDE)
    viaOutside.exploration.loadRoot()
    await settle()
    viaOutside.exploration.expandNode(RIGHT)
    await settle()

    expect(drawn(viaOutside.graph)).toEqual(drawn(viaRight.graph))
  })
})
