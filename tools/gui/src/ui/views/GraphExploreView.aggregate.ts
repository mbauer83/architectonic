/**
 * Pure view-model for scale-adaptive exploration: turns a server `AggregationSummary`
 * plus a client expand/collapse set into the node/edge lists the force graph renders.
 * Collapsed aggregates render as super-nodes with member counts; expanding one swaps in
 * its member entities (from the returned result) while every other aggregate stays
 * collapsed, with mixed edges re-bundled per (entity, aggregate, type, provenance).
 */

import type { AggregationSummary, ConnectionItemSummary, EntityItemSummary } from '../../domain'

export interface AggregateViewNode {
  readonly id: string
  readonly label: string
  readonly type: string
  readonly isAggregate: boolean
  readonly memberCount: number
}

export interface AggregateViewEdge {
  readonly source: string
  readonly target: string
  readonly connType: string
  readonly provenance: 'modeled' | 'derived-certain' | 'derived-potential'
  readonly bundledCount: number
}

export interface AggregateView {
  readonly nodes: readonly AggregateViewNode[]
  readonly edges: readonly AggregateViewEdge[]
  /** Members of expanded aggregates NOT present in the returned (limited) result — the
   * honest "expand couldn't show everything" count. */
  readonly missingMemberCount: number
}

const provenanceOf = (certainty: 'certain' | 'potential' | null | undefined): AggregateViewEdge['provenance'] =>
  certainty == null ? 'modeled' : certainty === 'certain' ? 'derived-certain' : 'derived-potential'

export const isAggregateNodeId = (id: string): boolean => id.startsWith('agg:')

export const buildAggregateView = (
  aggregation: AggregationSummary,
  expandedIds: ReadonlySet<string>,
  entities: readonly EntityItemSummary[],
  connections: readonly ConnectionItemSummary[],
): AggregateView => {
  const entityById = new Map(entities.map((entity) => [entity.id, entity]))
  const aggregateByEntity = new Map<string, string>()
  for (const node of aggregation.nodes) {
    for (const memberId of node.member_ids) aggregateByEntity.set(memberId, node.id)
  }

  const nodes: AggregateViewNode[] = []
  let missingMemberCount = 0
  for (const aggregate of aggregation.nodes) {
    if (!expandedIds.has(aggregate.id)) {
      nodes.push({
        id: aggregate.id,
        label: `${aggregate.dimension_value} · ${aggregate.entity_type} (${aggregate.member_count})`,
        type: aggregate.entity_type,
        isAggregate: true,
        memberCount: aggregate.member_count,
      })
      continue
    }
    for (const memberId of aggregate.member_ids) {
      const member = entityById.get(memberId)
      if (!member) {
        missingMemberCount += 1
        continue
      }
      nodes.push({ id: member.id, label: member.name, type: member.type, isAggregate: false, memberCount: 1 })
    }
  }

  /** A rendered endpoint: the entity itself when its aggregate is expanded (and the
   * entity is present), else its collapsed aggregate; null drops the edge. */
  const renderedEndpoint = (entityId: string): string | null => {
    const aggregateId = aggregateByEntity.get(entityId)
    if (aggregateId === undefined) return null
    if (!expandedIds.has(aggregateId)) return aggregateId
    return entityById.has(entityId) ? entityId : null
  }

  const bundles = new Map<string, { source: string; target: string; connType: string; provenance: AggregateViewEdge['provenance']; count: number }>()
  const addBundle = (source: string, target: string, connType: string, provenance: AggregateViewEdge['provenance'], count: number) => {
    if (source === target && isAggregateNodeId(source)) return // intra-aggregate edges collapse away
    const key = `${source}|${target}|${connType}|${provenance}`
    const existing = bundles.get(key)
    if (existing) existing.count += count
    else bundles.set(key, { source, target, connType, provenance, count })
  }

  // Collapsed↔collapsed pairs come from the server bundles (complete, limit-independent);
  // any pair involving an expanded aggregate re-bundles from the returned connections.
  for (const edge of aggregation.edges) {
    if (expandedIds.has(edge.source_aggregate_id) || expandedIds.has(edge.target_aggregate_id)) continue
    addBundle(edge.source_aggregate_id, edge.target_aggregate_id, edge.connection_type, edge.provenance, edge.member_count)
  }
  for (const connection of connections) {
    const sourceAggregate = aggregateByEntity.get(connection.source)
    const targetAggregate = aggregateByEntity.get(connection.target)
    if (sourceAggregate === undefined || targetAggregate === undefined) continue
    if (!expandedIds.has(sourceAggregate) && !expandedIds.has(targetAggregate)) continue
    const source = renderedEndpoint(connection.source)
    const target = renderedEndpoint(connection.target)
    if (source === null || target === null) continue
    addBundle(source, target, connection.type, provenanceOf(connection.certainty), 1)
  }

  return {
    nodes,
    edges: [...bundles.values()].map((bundle) => ({
      source: bundle.source,
      target: bundle.target,
      connType: bundle.connType,
      provenance: bundle.provenance,
      bundledCount: bundle.count,
    })),
    missingMemberCount,
  }
}

/** Aggregation "worked" when it produced a materially smaller, still-partitioned view.
 * One super-node explains nothing; more super-nodes than the budget is no overview at
 * all — both get the choice prompt (filter / switch representation / pick an anchor). */
export const aggregationIneffective = (aggregation: AggregationSummary): boolean =>
  aggregation.nodes.length <= 1 || aggregation.nodes.length > aggregation.legibility_budget
