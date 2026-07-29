import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import type { ViewpointExecutionResult } from '../../domain'
import {
  aggregationIneffective, buildAggregateView, isAggregateNodeId,
} from '../views/GraphExploreView.aggregate'

interface GraphMutators {
  clear: () => void
  addNode: (node: { id: string; label: string; type: string }) => void
  addEdge: (edge: { source: string; target: string; connType: string }) => void
  finalize: () => void
}

/**
 * Scale-adaptive exploration state: when an execution result carries a server
 * `aggregation` block (population over the legibility budget), the graph opens as
 * collapsed super-nodes; expand/collapse is pure client state re-rendered through the
 * same mutators the flat population uses. Exposes the banner inputs (hint when
 * aggregation cannot reduce the view, missing-member count for truncated expansions).
 */
export function useAggregatedExploration(
  result: Ref<ViewpointExecutionResult | null>,
  graph: GraphMutators,
) {
  const expandedAggregates = ref<Set<string>>(new Set())
  const missingMemberCount = ref(0)
  const activeAggregation = computed(() => result.value?.aggregation ?? null)
  const aggregationHint = computed(() => {
    const aggregation = activeAggregation.value
    return aggregation !== null && aggregationIneffective(aggregation)
      ? 'Aggregation cannot reduce this view to a readable overview — filter to a subgroup, switch to the table representation, or pick an anchor entity.'
      : null
  })

  const populateFromResult = () => {
    const execution = result.value
    if (!execution) return
    graph.clear()
    if (execution.aggregation) {
      const view = buildAggregateView(
        execution.aggregation, expandedAggregates.value, execution.entities, execution.connections,
      )
      missingMemberCount.value = view.missingMemberCount
      for (const node of view.nodes) {
        graph.addNode({ id: node.id, label: node.label, type: node.isAggregate ? node.type : node.id.split('@')[0] })
      }
      for (const edge of view.edges) {
        graph.addEdge({
          source: edge.source,
          target: edge.target,
          connType: `${edge.connType}${edge.bundledCount > 1 ? ` ×${edge.bundledCount}` : ''}`,
        })
      }
    } else {
      missingMemberCount.value = 0
      for (const entity of execution.entities) {
        graph.addNode({ id: entity.id, label: entity.name, type: entity.id.split('@')[0] })
      }
      for (const connection of execution.connections) {
        graph.addEdge({ source: connection.source, target: connection.target, connType: connection.type })
      }
    }
    graph.finalize()
  }

  const toggleAggregate = (aggregateId: string) => {
    const next = new Set(expandedAggregates.value)
    if (next.has(aggregateId)) next.delete(aggregateId)
    else next.add(aggregateId)
    expandedAggregates.value = next
    populateFromResult()
  }

  const resetExpansion = () => { expandedAggregates.value = new Set() }

  return {
    activeAggregation, aggregationHint, missingMemberCount,
    populateFromResult, toggleAggregate, resetExpansion, isAggregateNodeId,
  }
}
