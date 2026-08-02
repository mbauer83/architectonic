import { Effect } from 'effect'
import { makeHttpModelRepository } from '../../src/adapters/http/HttpModelRepository'
import type { ModelRepository } from '../../src/ports/ModelRepository'

/**
 * Identifiers the detail reads need, discovered from the collection reads rather than written down.
 *
 * A hard-coded id would make the harness depend on live model content, which CLAUDE.md forbids and
 * which would break the first time somebody authored an entity. Discovery instead: each seed is
 * "the first member of a collection the server reports", and a seed that comes back absent makes
 * the steps needing it *fail with that reason* rather than pass — an unexercised branch reported as
 * success is the green lie the harness is a response to, and an undiscoverable seed is a real gap in
 * the fixture (handoff §1.4).
 */
export interface ConformanceSeed {
  readonly entityId: string | null
  readonly entityType: string | null
  readonly connectionId: string | null
  readonly connectionSourceId: string | null
  readonly connectionTargetId: string | null
  readonly diagramId: string | null
  readonly matrixId: string | null
  readonly documentId: string | null
  readonly diagramTypeKey: string | null
  readonly datatypeTypeId: string | null
  readonly groupKind: string | null
  readonly groupSlug: string | null
  readonly viewpointSlug: string | null
  /**
   * An entity whose deletion plan is a *plan* rather than a refusal.
   *
   * The delete preview answers 400 for a referenced entity, listing its dependents as prose in the
   * message. So the first entity in the list will not do: almost everything in a real repository is
   * referenced by something, and a step seeded with one of those would assert the refusal rather
   * than the contract. Found by probing, because "unreferenced" is not a filter the list read offers
   * — the connection counts narrow it, and a diagram placement blocks a deletion the counts say
   * nothing about.
   */
  readonly deletableEntityId: string | null
}

const runOrNull = async <A>(effect: Effect.Effect<A, unknown>): Promise<A | null> => {
  const outcome = await Effect.runPromise(Effect.either(effect))
  return outcome._tag === 'Right' ? outcome.right : null
}

const first = <A>(items: readonly A[] | null | undefined): A | null =>
  items !== null && items !== undefined && items.length > 0 ? items[0] : null

/** The axis kinds a group list is keyed by, in the order a seed should prefer them. */
const GROUP_AXES = [
  'model-projects',
  'diagram-collections',
  'document-collections',
  'analysis-collections',
] as const

export const discoverSeed = async (repo: ModelRepository): Promise<ConformanceSeed> => {
  // A wide page on purpose: the delete-preview seed needs an *unreferenced* entity, and in a
  // repository that is actually used those are rare and late in the ordering.
  const entities = await runOrNull(repo.listEntities({ limit: 200 }))
  const entity = first(entities?.items)
  const diagrams = await runOrNull(repo.listDiagrams({}))
  const documents = await runOrNull(repo.listDocuments({ limit: 5 }))
  const diagramTypes = await runOrNull(repo.listDiagramTypes())
  const groups = await runOrNull(repo.listGroups())
  const viewpoints = await runOrNull(repo.listViewpointDefinitions())
  const datatypes = await runOrNull(repo.getDatatypeTypes({ limit: 5 }))

  // A connection is addressed by its own artifact id, and the only place one is published is the
  // connection list of an entity that has one — so this walks the page rather than assuming the
  // first entity has an edge.
  let connection: { artifact_id: string; source: string; target: string } | null = null
  for (const candidate of entities?.items ?? []) {
    const connections = await runOrNull(repo.getConnections(candidate.artifact_id))
    const found = first(connections ?? [])
    if (found !== null) {
      connection = found
      break
    }
  }

  // The matrix reads address a diagram whose type is a matrix; an ordinary diagram answers with a
  // body of a different shape, and that would be reported as the harness's own fault.
  const matrix = (diagrams?.items ?? []).find((d) => d.diagram_type.includes('matrix')) ?? null

  const axis = GROUP_AXES.find((kind) => (groups?.[kind] ?? []).length > 0) ?? null

  // Cheapest candidates first: an entity nothing connects to is the only one that *might* also be on
  // no diagram, and the plan itself is the only authority on whether it is.
  let deletable: string | null = null
  const unconnected = (entities?.items ?? []).filter(
    (e) => ((e.conn_in ?? 0) + (e.conn_sym ?? 0) + (e.conn_out ?? 0)) === 0,
  )
  for (const candidate of unconnected) {
    const plan = await runOrNull(repo.previewDeleteEntity(candidate.artifact_id))
    if (plan !== null) {
      deletable = candidate.artifact_id
      break
    }
  }

  return {
    deletableEntityId: deletable,
    entityId: entity?.artifact_id ?? null,
    entityType: entity?.artifact_type ?? null,
    connectionId: connection?.artifact_id ?? null,
    connectionSourceId: connection?.source ?? null,
    connectionTargetId: connection?.target ?? null,
    diagramId: first(diagrams?.items)?.artifact_id ?? null,
    matrixId: matrix?.artifact_id ?? null,
    documentId: first(documents?.items)?.artifact_id ?? null,
    diagramTypeKey: first(diagramTypes ?? [])?.key ?? null,
    datatypeTypeId: first(datatypes?.classifiers ?? [])?.type_id ?? null,
    groupKind: axis,
    groupSlug: axis === null ? null : (first(groups?.[axis]) ?? null)?.slug ?? null,
    viewpointSlug: first(viewpoints ?? [])?.slug ?? null,
  }
}

export const conformanceRepository = (): ModelRepository => makeHttpModelRepository()
