/**
 * What the edit panel offers to bring onto a diagram (sketch 01·8, D15): the relations the model holds
 * between elements the diagram draws and does not draw itself, and elements found or nearby, each told
 * apart by whether the diagram already draws it — a drawn one is selected, never added again.
 *
 * Everything is compared by stable id (`stableEntityId`, `stableConnectionId`): a diagram's lists and
 * the model's reads may spell the same element with different slugs.
 */
import { stableConnectionId, stableEntityId } from '../artifactId'
import type { ModelRelation } from '../diagramReadingLists'

/** A relation the model holds between two drawn elements, which the diagram does not draw. */
export interface UndrawnRelation {
  readonly id: string
  readonly type: string
  readonly sourceName: string
  readonly targetName: string
  /** The drawings of its two ends, source first: what hovering its row outlines. */
  readonly ends: readonly [string, string]
}

/**
 * The relations among *candidates* whose two ends *drawn* holds (stable id → drawing alias) and which
 * neither the diagram nor the session draws (*drawnRelations*, by stable id), in the model's order.
 */
export const undrawnRelationsAmong = (
  candidates: readonly ModelRelation[], drawn: ReadonlyMap<string, string>, drawnRelations: ReadonlySet<string>,
): readonly UndrawnRelation[] => {
  const seen = new Set<string>()
  return candidates.flatMap((relation): UndrawnRelation[] => {
    const key = stableConnectionId(relation.artifact_id)
    const [source, target] = [drawn.get(stableEntityId(relation.source)), drawn.get(stableEntityId(relation.target))]
    if (seen.has(key) || drawnRelations.has(key) || source === undefined || target === undefined) return []
    seen.add(key)
    return [{
      id: relation.artifact_id, type: relation.conn_type, sourceName: relation.source_name,
      targetName: relation.target_name, ends: [source, target],
    }]
  })
}

/** An element the panel lists, with the alias it is drawn under when the diagram draws it already. */
export interface Discovered<T> {
  readonly entity: T
  readonly drawnAs?: string
}

/** *found*, each once, with the drawing *drawn* holds for it; drawn ones after the rest, so adding leads. */
export const discovered = <T extends { readonly artifact_id: string }>(
  found: readonly T[], drawn: ReadonlyMap<string, string>,
): readonly Discovered<T>[] => {
  const once = [...new Map(found.map((one) => [stableEntityId(one.artifact_id), one])).values()]
  const marked = once.map((entity) => ({ entity, drawnAs: drawn.get(stableEntityId(entity.artifact_id)) }))
  return [...marked.filter((one) => one.drawnAs === undefined), ...marked.filter((one) => one.drawnAs !== undefined)]
}
