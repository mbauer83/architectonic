/**
 * Pure helpers for `QueryBindingsPanel.vue`: which earlier binding names a binding's own
 * criteria may reference (bindings evaluate in declaration order — a binding may reference
 * only bindings declared before it, never itself or a later one, mirroring the backend's
 * `unknown-binding` dependency check), and small list-mutation helpers kept out of the
 * component so they're vitest-covered without mounting Vue.
 */

import type { QueryBindingNode } from '../../domain/viewpointBindings'
import { mkQueryBinding } from '../../domain/viewpointBindings'

/** Names of bindings declared strictly before `index` — the only bindings this binding's
 * own criteria/tuple members may legally reference. */
export const earlierBindingNames = (bindings: readonly QueryBindingNode[], index: number): readonly string[] =>
  bindings.slice(0, index).filter((b) => b.name.length > 0).map((b) => b.name)

export const addBinding = (bindings: readonly QueryBindingNode[]): QueryBindingNode[] => [...bindings, mkQueryBinding()]

export const removeBindingAt = (bindings: readonly QueryBindingNode[], index: number): QueryBindingNode[] =>
  bindings.filter((_, i) => i !== index)

export const updateBindingAt = (
  bindings: readonly QueryBindingNode[],
  index: number,
  patch: Partial<QueryBindingNode>,
): QueryBindingNode[] => bindings.map((b, i) => (i === index ? { ...b, ...patch } : b))

/** `include_in_result` is only legal for a binding whose declared shape is still
 * entity-valued — `project`ing or `aggregate`ing turns it into a scalar, and tuples are
 * never entity-valued (mirrors the backend's `is_entity_value` check). */
export const canIncludeInResult = (binding: QueryBindingNode): boolean =>
  binding.mode === 'select' && binding.select === 'entities' && binding.project === null && binding.aggregate === null
