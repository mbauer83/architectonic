/**
 * Which values a loaded graph offers to filter on, and what a selection hides.
 *
 * The meta-ontology declares how it classifies things: a chain of levels per concept kind, served
 * by `/api/ontology/classification-levels`. This reads a thing's value for a level through the
 * level's declared **`source`** — never through its `id`. That is the whole of what keeps the
 * filter meta-ontology-shaped: `archimate-4-0` happens to name its entity levels `domain`,
 * `entity_type` and `specialization`, and a filter keyed on those names works perfectly against
 * the one meta-ontology that declares them while being ArchiMate-shaped by construction. The
 * failure is recorded in `classification_levels.py`'s own docstring, about the scratchpad's first
 * refinement design, and `graphFacets.test.ts` proves the escape with a fixture chain that shares
 * no level id with ArchiMate's.
 *
 * Only values **present in the loaded graph** are offered, because a facet listing the whole
 * catalogue is a list of things that will not change the picture.
 */

/** A declared level, as it crosses the wire: `id` is an opaque string, never a union member. */
export interface ClassificationLevel {
  readonly id: string
  readonly label: string
  /** Where a thing's value for this level is read from. The structural half of the declaration. */
  readonly source: string
  readonly required: boolean
}

/** The levels the meta-ontology declares, keyed by concept kind. */
export interface ClassificationLevels {
  readonly entity: readonly ClassificationLevel[]
  readonly relation: readonly ClassificationLevel[]
}

/** What this module needs of a node. A structural subset, so it is not the canvas's to change. */
export interface FacetableNode {
  readonly id: string
  readonly domain?: string
  readonly artifactType?: string
  readonly specializations?: readonly string[]
}

/** What this module needs of an edge. */
export interface FacetableEdge {
  readonly source: string
  readonly target: string
  readonly connType: string
  readonly specializations?: readonly string[]
}

/** Excluded values per level id. A level absent from the map excludes nothing. */
export type FacetSelection = Readonly<Record<string, readonly string[]>>

/** One level's offerable values, in display order, with the level's own label. */
export interface FacetOptions {
  readonly level: ClassificationLevel
  readonly values: readonly string[]
}

/**
 * A thing's values at one level.
 *
 * Returns a list because a level may be many-valued — an entity carries any number of
 * specializations — and empty when the thing has no value there, which is what `required: false`
 * means. An unknown source yields nothing rather than throwing: a meta-ontology may declare a
 * source this client has no way to read, and the honest answer is to offer no values for it
 * rather than to guess or to fail the whole graph.
 */
export function valuesAt(
  source: string,
  thing: FacetableNode | FacetableEdge,
): readonly string[] {
  const node = thing as FacetableNode
  const edge = thing as FacetableEdge
  if (source === 'hierarchy') return node.domain ? [node.domain] : []
  if (source === 'type') {
    const own = node.artifactType ?? edge.connType
    return own ? [own] : []
  }
  if (source === 'specializations') return thing.specializations ?? []
  return []
}

const sortedUnique = (values: Iterable<string>): readonly string[] =>
  [...new Set(values)].sort((a, b) => a.localeCompare(b))

/** The values each declared level actually takes across *things*, in display order. */
export function facetOptions(
  levels: readonly ClassificationLevel[],
  things: readonly (FacetableNode | FacetableEdge)[],
): readonly FacetOptions[] {
  return levels
    .map((level) => ({
      level,
      values: sortedUnique(things.flatMap((thing) => valuesAt(level.source, thing))),
    }))
    // A level nothing in this graph has a value for offers no choice, so it is not shown. The
    // level is still declared; it simply has nothing to say about what is loaded.
    .filter((options) => options.values.length > 0)
}

/**
 * Whether *thing* is hidden by *selection*.
 *
 * Excluded at any level hides it. A thing with no value at a level cannot be excluded by that
 * level — otherwise excluding one specialization would hide every element that has none, which
 * reads as the filter breaking rather than as filtering.
 */
export function isExcluded(
  selection: FacetSelection,
  levels: readonly ClassificationLevel[],
  thing: FacetableNode | FacetableEdge,
): boolean {
  return levels.some((level) => {
    const excluded = selection[level.id]
    if (!excluded || excluded.length === 0) return false
    const own = valuesAt(level.source, thing)
    return own.length > 0 && own.every((value) => excluded.includes(value))
  })
}

/** How many values the selection excludes in total — what the collapsed headline reports. */
export function excludedCount(selection: FacetSelection): number {
  return Object.values(selection).reduce((total, values) => total + values.length, 0)
}

/**
 * The graph *narrowed* to what the selection leaves.
 *
 * An edge goes when either endpoint goes, as well as when the relation itself is excluded: an
 * edge to a node that is not drawn is a line to nowhere, which is the same defect B31 fixed at
 * the other end.
 */
export function narrowed<N extends FacetableNode, E extends FacetableEdge>(
  levels: ClassificationLevels,
  selection: FacetSelection,
  nodes: readonly N[],
  edges: readonly E[],
): { readonly nodes: readonly N[]; readonly edges: readonly E[] } {
  const keptNodes = nodes.filter((node) => !isExcluded(selection, levels.entity, node))
  const kept = new Set(keptNodes.map((node) => node.id))
  return {
    nodes: keptNodes,
    edges: edges.filter(
      (edge) =>
        kept.has(edge.source) &&
        kept.has(edge.target) &&
        !isExcluded(selection, levels.relation, edge),
    ),
  }
}
