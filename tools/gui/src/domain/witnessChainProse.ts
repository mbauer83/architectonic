/**
 * Witness-chain popover support: a derived relationship is never itself a modeled
 * connection — `via_connection_ids` names the set of real connections that compose it.
 * That set is NOT guaranteed to be given in source-to-target traversal order (the
 * derivation engine can extend a partial chain from either end as it composes hops), so
 * reconstructing readable prose requires walking the edge set as a graph rather than
 * trusting array order: start at the known source, and at each step pick whichever
 * remaining connection is incident to the current position. This turns that resolved walk
 * into prose with each entity name addressable as a clickable link. The async fetch
 * orchestration lives in the composable that calls this, so the walk itself stays
 * unit-testable without a network.
 */

import type { ConnectionRecord } from './schemas/connections'

export interface WitnessChainStep {
  readonly connectionId: string
  readonly connectionType: string
  readonly fromEntityId: string
  readonly fromEntityName: string
  readonly toEntityId: string
  readonly toEntityName: string
}

/** Reconstructs the source-to-target order of a witness chain from an unordered set of
 * already-fetched connection records, starting from `sourceEntityId`. At each step, picks
 * any not-yet-used connection with an endpoint at the current position and moves to its
 * other endpoint — the set forms a simple path (no cycles, no branching) by construction,
 * so this greedy walk always finds the full chain when the connections are all resolvable.
 * Stops (returns the steps found so far) once no remaining connection touches the current
 * position — a broken or incomplete chain is a staleness finding for the caller to
 * surface, never a reason to guess or fabricate a step. */
export const walkWitnessChain = (
  sourceEntityId: string,
  connectionIds: readonly string[],
  connectionById: ReadonlyMap<string, ConnectionRecord>,
): readonly WitnessChainStep[] => {
  const steps: WitnessChainStep[] = []
  const unused = new Set(connectionIds)
  let currentId = sourceEntityId
  while (unused.size > 0) {
    const nextConnectionId = [...unused].find((id) => {
      const connection = connectionById.get(id)
      return connection !== undefined && (connection.source === currentId || connection.target === currentId)
    })
    if (nextConnectionId === undefined) break
    const connection = connectionById.get(nextConnectionId)!
    unused.delete(nextConnectionId)
    const nextId = connection.source === currentId ? connection.target : connection.source
    steps.push({
      connectionId: nextConnectionId,
      connectionType: connection.conn_type,
      fromEntityId: currentId,
      fromEntityName: (currentId === connection.source ? connection.source_name : connection.target_name) ?? currentId,
      toEntityId: nextId,
      toEntityName: (nextId === connection.source ? connection.source_name : connection.target_name) ?? nextId,
    })
    currentId = nextId
  }
  return steps
}

export interface ProseSegment {
  readonly text: string
  readonly entityId?: string
}

/** One segment per entity name (clickable, `entityId` set) interleaved with plain-text
 * arrows labelled by connection type — e.g. "A —(serving)→ B —(assignment)→ C". Empty
 * input (a fully broken chain) renders as no segments; the caller shows its own
 * broken-chain message rather than this producing placeholder text. */
export const witnessChainProse = (steps: readonly WitnessChainStep[]): readonly ProseSegment[] => {
  if (steps.length === 0) return []
  const segments: ProseSegment[] = [{ text: steps[0].fromEntityName, entityId: steps[0].fromEntityId }]
  for (const step of steps) {
    segments.push({ text: ` —(${step.connectionType.replace('archimate-', '')})→ ` })
    segments.push({ text: step.toEntityName, entityId: step.toEntityId })
  }
  return segments
}
