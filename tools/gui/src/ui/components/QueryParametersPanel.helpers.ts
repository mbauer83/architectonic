/**
 * Pure list-mutation helpers for `QueryParametersPanel.vue` — kept out of the component so
 * they're vitest-covered without mounting Vue, same convention as the bindings panel.
 */

import type { QueryParameterNode } from '../../domain/viewpointBindings'
import { mkQueryParameter } from '../../domain/viewpointBindings'

export const addParameter = (parameters: readonly QueryParameterNode[]): QueryParameterNode[] => [
  ...parameters, mkQueryParameter(),
]

export const removeParameterAt = (parameters: readonly QueryParameterNode[], index: number): QueryParameterNode[] =>
  parameters.filter((_, i) => i !== index)

export const updateParameterAt = (
  parameters: readonly QueryParameterNode[],
  index: number,
  patch: Partial<QueryParameterNode>,
): QueryParameterNode[] => parameters.map((p, i) => (i === index ? { ...p, ...patch } : p))
