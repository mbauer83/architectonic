/**
 * What an element drawn as a container may hold (sketch 03·2): the types the ontology permits a
 * relation of the containment kind to from the container's type, among the relations this diagram
 * type accepts. The kind is the ontology's own schema vocabulary (`relationship_kind`), so no
 * ontology's relation names are spelled here.
 */
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'

const CONTAINMENT = 'containment'

/** The types *outgoing* reaches by one of *containing*: the target types with a containment relation. */
export const containedTypes = (
  outgoing: Readonly<Record<string, readonly string[]>>, containing: ReadonlySet<string>,
): ReadonlySet<string> =>
  new Set(Object.entries(outgoing)
    .flatMap(([target, kinds]) => (kinds.some((kind) => containing.has(kind)) ? [target] : [])))

/**
 * The relationships of the containment kind the ontology permits from a *container* type to a *part*
 * type: what nesting one in the other may mean (03·10), and none where it may not be nested at all.
 */
export const containmentKinds = async (
  svc: Pick<ModelService, 'getOntologyPair'>, container: string, part: string,
): Promise<readonly string[]> => {
  const pair = await Effect.runPromise(svc.getOntologyPair(container, part))
  return pair.connection_types.filter((kind) => pair.relationship_kind_map[kind] === CONTAINMENT)
}

export const partsTypes = async (
  svc: Pick<ModelService, 'getOntologyClassification' | 'getDiagramTypeConnectionTypes'>,
  diagramType: string, containerType: string,
): Promise<ReadonlySet<string>> => {
  const [classification, relations] = await Promise.all([
    Effect.runPromise(svc.getOntologyClassification(containerType)),
    Effect.runPromise(svc.getDiagramTypeConnectionTypes(diagramType)),
  ])
  const containing = new Set(relations.flatMap((item) =>
    (item.relationship_kind === CONTAINMENT && typeof item.connection_type === 'string' ? [item.connection_type] : [])))
  return containedTypes(classification.outgoing, containing)
}
