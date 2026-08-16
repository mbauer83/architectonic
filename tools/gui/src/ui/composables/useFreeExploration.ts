import { Effect } from 'effect'
import type { Ref } from 'vue'
import type { ConnectionList } from '../../domain'
import type { ModelService } from '../../application/ModelService'
import type { GraphNode } from './useForceGraph'
import { friendlyEntityName } from '../views/GraphExploreView.helpers'

/**
 * Incremental exploration outward from a root entity: load its neighbourhood, expand a node
 * on demand, and keep node metadata filled in as new nodes arrive.
 *
 * The counterpart to viewpoint-driven execution, which renders a fixed population computed
 * server-side. Here the population grows one hop at a time in response to the user, so the
 * two differ in what triggers a layout and in what "the current result" even means. They
 * live apart for that reason rather than as branches inside one loader.
 *
 * What they do **not** differ about is which relations exist between the elements on screen.
 * The drawn edges are the model's edges among the drawn nodes — the same invariant the
 * viewpoint path states — so two people looking at the same nodes see the same graph however
 * they got there. Legibility is a filter over a complete set, never a fetch strategy.
 */
//: How many times to sweep for nodes still missing a domain. Two would cover one concurrent
//: expansion; three leaves room for a second without ever looping unboundedly.
const DOMAIN_RESOLUTION_PASSES = 3

/** The three reads exploration makes, and no more — the shape `useWitnessChain` already uses for
 * the same reason: a dependency typed as the whole service cannot be stood in for without
 * asserting past 100 methods it never calls. */
export type FreeExplorationReads = Pick<
  ModelService, 'getEntity' | 'getConnections' | 'getConnectionsAmong'
>

export interface FreeExplorationDeps {
  svc: FreeExplorationReads
  nodes: Ref<GraphNode[]>
  edges: Ref<unknown[]>
  rootId: Ref<string>
  addNode: (node: {
    id: string; label: string; type: string; addedBy?: string
    specializations?: readonly string[]
  }) => void
  addEdge: (edge: {
    source: string; target: string; connType: string; description?: string
    srcMultiplicity?: string; tgtMultiplicity?: string; specializations?: readonly string[]
  }) => void
  markExpanded: (id: string) => void
  spreadAroundParent: (id: string) => void
  /**
   * Re-apply whichever layout the user currently has selected, centred on `centerId`.
   *
   * Supplied by the view rather than decided here. Which arrangement a mode means is one rule,
   * and the toolbar needs to answer it too; keeping the answer in one place is what stops the
   * two drifting as modes are added — radial was added to this surface long after force and
   * cluster, and had to work on both paths without being written down twice.
   */
  relayout: (centerId?: string) => void
  isAggregateNodeId: (id: string) => boolean
  selectNode: (id: string) => void
}

export function useFreeExploration(deps: FreeExplorationDeps) {
  const {
    svc, nodes, edges, rootId, addNode, addEdge, markExpanded, spreadAroundParent,
    relayout, isAggregateNodeId, selectNode,
  } = deps

  /** What the model knows about an entity that the graph renders: colour, glyph, label, degree. */
  interface EntityFacts {
    domain: string
    artifactType: string
    label: string
    totalConns: number
    specializations: readonly string[]
  }

  /**
   * Look up one entity's renderable facts.
   *
   * An aggregate stands for a group of entities rather than being one, so there is nothing
   * to look up: its id is synthetic and the entity read answers 404. The rejection is swallowed,
   * which would make the wasted request per cluster visible only as console noise.
   */
  const fetchEntityFacts = async (id: string): Promise<EntityFacts | null> => {
    if (isAggregateNodeId(id)) return null
    return Effect.runPromise(svc.getEntity(id))
      .then((d) => ({
        domain: d.domain,
        artifactType: d.artifact_type,
        label: d.name || friendlyEntityName(id),
        totalConns: (d.conn_in ?? 0) + (d.conn_sym ?? 0) + (d.conn_out ?? 0),
        specializations: d.specializations ?? [],
      }))
      .catch(() => null)
  }

  const applyFacts = (n: GraphNode, facts: EntityFacts): void => {
    n.domain = facts.domain
    n.artifactType = facts.artifactType
    n.label = facts.label
    n.totalConns = facts.totalConns
    n.specializations = facts.specializations
  }

  /**
   * Fill in a node's facts in place, for a node already on the canvas.
   *
   * The straggler path only: a node added by an expansion that overlapped this one missed the
   * prefetch below, and would otherwise stay grey until something else moved it.
   */
  const resolveNodeDomain = async (n: GraphNode): Promise<void> => {
    const facts = await fetchEntityFacts(n.id)
    if (facts) applyFacts(n, facts)
  }

  /**
   * Fold a fetched neighbourhood into the graph and re-lay it out.
   *
   * The neighbourhood is resolved *before* any of it is published, and then added, positioned
   * and set moving in one synchronous pass. Publishing first and resolving after — which is
   * what this used to do — put the new nodes on screen grey and unlabelled at their seeded
   * scatter positions, held them there for the length of a fetch per node, and then snapped
   * them somewhere else the moment the domains arrived and the layout could run. Three visible
   * states for one action, two of which were nothing the user asked to see.
   *
   * The root load already worked this way, for the same reason; see `loadRoot`.
   */
  /**
   * Every model connection among the nodes the graph is about to hold.
   *
   * Asked for as one question over the whole population rather than assembled from each node's
   * own connections. A connection between two neighbours is incident to neither the focus nor
   * any node expanded so far, so no star query ever names it: it was not filtered out, it was
   * never asked for, and the drawn edge set therefore depended on click order rather than on the
   * model. Aggregates stand for groups rather than being entities, so they are left out of the
   * question — asking about a synthetic id would only widen it with nothing.
   */
  const edgesAmong = async (nodeIds: Iterable<string>): Promise<ConnectionList> => {
    const entityIds = [...new Set(nodeIds)].filter((id) => !isAggregateNodeId(id))
    return Effect.runPromise(svc.getConnectionsAmong(entityIds))
  }

  const applyNeighbourhood = async (entityId: string, conns: ConnectionList): Promise<void> => {
    const beforeIds = new Set(nodes.value.map((n) => n.id))
    const arrivals = new Map<string, string | undefined>()
    for (const c of conns) {
      const otherId = c.source === entityId ? c.target : c.source
      if (!arrivals.has(otherId)) {
        arrivals.set(otherId, beforeIds.has(otherId) ? undefined : entityId)
      }
    }

    // The focus joins the round unless the canvas already knows it — on the root load the graph
    // holds nothing at all, and on a straggler path it holds a node with no domain yet. Left out,
    // it painted grey and id-labelled while every neighbour arrived coloured, and resolved a fetch
    // later, at which point the domain it added to the legend re-framed the whole graph.
    const focusOnCanvas = nodes.value.find((n) => n.id === entityId)
    const unresolved = focusOnCanvas?.domain ? [...arrivals.keys()] : [entityId, ...arrivals.keys()]

    // One parallel round for the whole hop, before anything is shown. This costs no extra
    // waiting: the layout could never run until these landed anyway — and the complete edge set
    // is asked for in the same round, so it arrives with them rather than after a second wait.
    const factsById = new Map<string, EntityFacts>()
    const [complete] = await Promise.all([
      edgesAmong([...beforeIds, entityId, ...arrivals.keys()]),
      ...unresolved.map(async (id) => {
        const facts = await fetchEntityFacts(id)
        if (facts) factsById.set(id, facts)
      }),
    ])

    // Synchronous from here: no await, so the nodes appear coloured, labelled and already
    // seeded around their parent, in a single paint, and then animate. The focus is added here
    // too when the canvas does not hold it, so that the root and its hop are one transition; see
    // `loadRoot`.
    if (!focusOnCanvas) {
      addNode({ id: entityId, label: friendlyEntityName(entityId), type: entityId.split('@')[0] })
    }
    for (const [id, addedBy] of arrivals) {
      addNode({ id, label: friendlyEntityName(id), type: id.split('@')[0], addedBy })
    }
    for (const [id, facts] of factsById) {
      const node = nodes.value.find((n) => n.id === id)
      if (node) applyFacts(node, facts)
    }
    for (const c of complete) {
      addEdge({
        source: c.source, target: c.target, connType: c.conn_type, description: c.content_text,
        srcMultiplicity: c.src_multiplicity || undefined,
        tgtMultiplicity: c.tgt_multiplicity || undefined,
        specializations: c.specializations ?? [],
      })
    }
    markExpanded(entityId)
    spreadAroundParent(entityId)

    // Expansion is the one moment the graph should move, and it has to be *seen* to move: a
    // rearrangement that happens between two paints reads as the graph vanishing and coming
    // back already expanded, with no way to tell which nodes are new or where the ones being
    // watched went.
    relayout(entityId)

    // Stragglers: expanding a second node while this one was still loading adds nodes *after*
    // the prefetch above, so they arrive unresolved and the layout that just ran did not know
    // their domain. Bounded rather than "until none remain": resolution can legitimately fail
    // (an aggregate has no record to fetch), and a loop keyed on success would never end.
    for (let pass = 0; pass < DOMAIN_RESOLUTION_PASSES; pass++) {
      const pending = nodes.value.filter((n) => !n.domain && !isAggregateNodeId(n.id))
      if (pending.length === 0) return
      await Promise.all(pending.map(resolveNodeDomain))
      relayout(entityId)
    }
  }

  const expandNode = (entityId: string): void => {
    void Effect.runPromise(svc.getConnections(entityId, 'any'))
      .then((conns: ConnectionList) => applyNeighbourhood(entityId, conns))
  }

  /**
   * Open the graph on `rootId` and its first hop.
   *
   * Root and first hop are published as one transition. Adding the root on its own first
   * makes it a population of one, which the canvas dutifully frames — a viewport filled by a
   * single node — and the neighbourhood arriving a moment later refits to something an order
   * of magnitude larger. The user sees a zoom flip that corresponds to no state they asked
   * for. The sidebar is a separate concern and still fills immediately.
   *
   * Which is why the root is *not* added here. It used to be, and that was one transition for as
   * long as the hop published synchronously; resolving the hop before showing it — the fix for
   * neighbours arriving grey — put a fetch between the two, and the lone root held the screen for
   * a third of a second again. `applyNeighbourhood` adds whichever of the two the canvas is
   * missing, in its own synchronous pass, so the pair cannot come apart a third time.
   */
  const loadRoot = (): void => {
    if (!rootId.value) return
    const id = rootId.value
    nodes.value = []
    edges.value = []
    selectNode(id)
    void Effect.runPromise(svc.getConnections(id, 'any')).then(async (conns: ConnectionList) => {
      if (rootId.value !== id) return // superseded by a newer root while the fetch was in flight
      await applyNeighbourhood(id, conns)
    })
  }

  return { resolveNodeDomain, expandNode, loadRoot }
}
