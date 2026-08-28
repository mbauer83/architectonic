import { Option, Schema } from 'effect'
import { C4NavigationSchema } from '../../domain/schemas/diagrams'
import type { C4Navigation, DiagramConnection, DiagramContextEntity } from '../../domain'

/** A diagram kind's own region of a read: whatever `read_diagram_extras` or
 * `build_context_extras` returned, which this package cannot know the shape of. A consumer that
 * knows the kind decodes the part it came for — the two readers below are that, for the two kinds
 * the GUI renders specially. */
type TypeExtras = Readonly<Record<string, unknown>> | undefined

/** The matrix kind's rendered body, or null when this is not a matrix read. */
export const matrixBodyOf = (extras: TypeExtras): string | null => {
  const body = extras?.matrix_body
  return typeof body === 'string' && body ? body : null
}

/** The C4 kind's navigation block, decoded rather than asserted: it arrives from a region the
 * envelope declares as the module's, so a shape claim about it has to be checked. */
export const c4NavigationOf = (extras: TypeExtras): C4Navigation | null =>
  extras?.c4_navigation === undefined
    ? null
    : Option.getOrNull(Schema.decodeUnknownOption(C4NavigationSchema)(extras.c4_navigation))

/**
 * Build alias→artifactId map for SVG interactivity.
 *
 * Stores the raw alias, a PlantUML-safe variant (non-alphanumeric chars → '_'), and that
 * variant with a leading '_'. The leading-'_' form mirrors the class-diagram renderer's
 * `_safe_alias` ('_' + sanitised id), which guarantees a PlantUML-valid alias; without it,
 * class-diagram SVG nodes (whose `data-qualified-name` carries the '_'-prefixed alias)
 * would never resolve and so would not be selectable.
 */
export function buildAliasToId(entities: ReadonlyArray<DiagramContextEntity>): Map<string, string> {
  const map = new Map<string, string>()
  for (const e of entities) {
    if (!e.display_alias) continue
    const safe = e.display_alias.replace(/[^a-zA-Z0-9_]/g, '_')
    for (const alias of [e.display_alias, safe, `_${safe}`]) {
      // First non-fragment id wins: prefer a canonical workspace id (CLF@…) over a
      // diagram-scoped '#fragment' id so the click target resolves to a loadable entity.
      const existing = map.get(alias)
      if (existing === undefined || (existing.includes('#') && !e.artifact_id.includes('#'))) {
        map.set(alias, e.artifact_id)
      }
    }
  }
  return map
}

/** True when the entity lives inside a diagram (no standalone file). */
export function isDiagramOnly(entity: { host_diagram_id?: string | null }): boolean {
  return !!entity.host_diagram_id
}

/** Matrix diagrams render their stored Markdown and must never call the SVG renderer. */
export function diagramNeedsSvg(diagramType: string | null | undefined): boolean {
  return !!diagramType && diagramType !== 'matrix'
}

/** One diagram a node can drill into, with the name a reader chooses it by. */
export type DrilldownTarget = { diagramId: string; name: string }

/**
 * Builds a map of entityId → the diagrams that node drills into.
 *
 * For L2→L3 children, the child carries its own scope_entity_id (the container
 * whose component diagram it is). For L1/L2 same-scope children, the child shares
 * the parent's scope entity — fall back to c4Nav.scope_entity_id.
 *
 * The value is a list, and that is the whole of this function's history: it used to be one id, and
 * the loop below overwrote it once per child, so a container with several component views drilled
 * into whichever happened to come last. A container may be drawn one concern at a time — a write
 * path, a read path, an assurance module — and no tie-break among those is right, because they are
 * peers and only the reader knows which one they meant.
 */
export function buildDrilldownByEntityId(
  c4Nav: C4Navigation | null | undefined,
): Record<string, DrilldownTarget[]> {
  if (!c4Nav) return {}
  const map: Record<string, DrilldownTarget[]> = {}
  for (const child of c4Nav.child_diagrams) {
    const entityId = child.scope_entity_id ?? c4Nav.scope_entity_id
    if (!entityId) continue
    ;(map[entityId] ??= []).push({ diagramId: child.diagram_id, name: child.diagram_name })
  }
  return map
}

export type ConnectionAliasMap = {
  queue: Map<string, DiagramConnection[]>
  fallback: Map<string, DiagramConnection>
}

/**
 * Build bidirectional alias-keyed lookup structures for SVG edge interactivity.
 *
 * `queue` holds ordered lists of connections per forward/reverse key so that
 * parallel edges between the same pair of nodes are each matched at most once.
 * `fallback` holds the first connection seen per key for unordered lookups.
 */
export function buildConnectionAliasMap(
  connections: ReadonlyArray<DiagramConnection>,
): ConnectionAliasMap {
  const queue = new Map<string, DiagramConnection[]>()
  const fallback = new Map<string, DiagramConnection>()
  for (const conn of connections) {
    if (!conn.source_alias || !conn.target_alias) continue
    const fwd = `${conn.source_alias}:${conn.target_alias}`
    const rev = `${conn.target_alias}:${conn.source_alias}`
    const q = queue.get(fwd) ?? []
    q.push(conn)
    queue.set(fwd, q)
    fallback.set(fwd, conn)
    if (!fallback.has(rev)) fallback.set(rev, conn)
  }
  return { queue, fallback }
}

/**
 * Resolve which DiagramConnection corresponds to an SVG edge between aliases a1 and a2.
 * Consumes from the queue first (for parallel edges), then falls back to the first seen.
 */
export function resolveConnection(
  a1: string,
  a2: string,
  { queue, fallback }: ConnectionAliasMap,
): DiagramConnection | undefined {
  const fwd = `${a1}:${a2}`
  const rev = `${a2}:${a1}`
  return (
    queue.get(fwd)?.shift()
    ?? queue.get(rev)?.shift()
    ?? fallback.get(fwd)
    ?? fallback.get(rev)
  )
}

/** Whether a load is arriving at a *different* diagram, and must therefore discard what is on screen.
 *
 * A reload of the diagram already shown is a refresh, and a refresh must keep the canvas mounted:
 * the browser ends fullscreen when its fullscreen element leaves the document, so replacing the
 * canvas drops the reader out of a fullscreen diagram. Every reload path reaches this — a save from
 * the sidebar, a sync, a write from the selection — and only a change of diagram is a reason to throw
 * the picture away, where the old one must not show under the new id.
 *
 * The query keeps its data across a refetch on its own; `reset()` is the only thing that discards it,
 * which is why the question is asked before calling that rather than inside it.
 */
export const isADifferentDiagram = (loaded: string | null, arriving: string): boolean =>
  loaded !== arriving

/** The matrix body rendered to HTML, or `null` when this diagram is not a matrix or carries none.
 *
 * Both halves are the condition: a `type_extras` body on a non-matrix diagram is not a matrix to
 * render, and a matrix with no body has nothing to show. */
export const matrixHtmlOf = (
  diagramType: string | undefined,
  typeExtras: TypeExtras,
  render: (body: string) => string,
): string | null => {
  const body = matrixBodyOf(typeExtras)
  return body === null || diagramType !== 'matrix' ? null : render(body)
}

/** Where "Edit" goes: a matrix is edited in its own view, everything else in the diagram editor. */
export const editRouteFor = <T>(
  diagramType: string | undefined,
  diagramId: string,
  matrixRoute: (id: string) => T,
  diagramRoute: (id: string) => T,
): T => (diagramType === 'matrix' ? matrixRoute(diagramId) : diagramRoute(diagramId))

/** The editable-metadata spec for each diagram-only entity type the config declares.
 *
 * Keyed by entity type so a detail panel resolves its own without the generic view knowing any type
 * names — the config is the only place those names live. */
export const editableMetadataByEntityType = <Spec>(
  config: { diagram_only_types?: readonly { entity_type: string; editable_metadata?: Spec }[] } | null,
): Record<string, Spec> => {
  const out: Record<string, Spec> = {}
  for (const own of config?.diagram_only_types ?? []) {
    if (own.editable_metadata) out[own.entity_type] = own.editable_metadata
  }
  return out
}
