/**
 * Which of the loaded relations a free exploration draws by default.
 *
 * Exploring outward from an entity reads as a star: the entity, what it is related to, and how. The
 * graph still holds every model relation among the drawn nodes — that is the invariant
 * `useFreeExploration` keeps, so the set never depends on click order — but the relations between
 * two neighbours are about neither the entity being explored nor anything expanded since, and on a
 * dense model they bury the star. They are drawn on request, never fetched on request.
 *
 * The focus is every node the reader has expanded, the root among them; a node the root load has not
 * finished expanding yet is still the focus, so the root is named explicitly as well.
 */

interface ExplorationNode {
  readonly id: string
  readonly expanded: boolean
}

interface Relation {
  readonly source: string
  readonly target: string
}

/** The nodes whose relations the exploration is about: the root and every expanded node. */
export const explorationFocus = (rootId: string, nodes: readonly ExplorationNode[]): ReadonlySet<string> =>
  new Set([rootId, ...nodes.filter((node) => node.expanded).map((node) => node.id)].filter((id) => id !== ''))

/** The relations with at least one end on the focus; a relation between two neighbours has neither. */
export const relationsOfFocus = <R extends Relation>(relations: readonly R[], focus: ReadonlySet<string>): R[] =>
  relations.filter((relation) => focus.has(relation.source) || focus.has(relation.target))
