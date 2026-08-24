import type { DiagramMapContext, DiagramElementMap } from '../../lib/diagramViewerExtensions'

/** A step's attached note as stored in the diagram-entities payload. */
export type StepNote = { side: string; text: string }

/**
 * The activity module's diagram-only types whose label the renderer wraps in a sentinel link, so a
 * diagram-local one can be resolved by its `display_alias`.
 *
 * The module declares five: swimlane, action, decision, fork, partition. `fork` is absent because
 * PlantUML accepts no link on one — `fork [[url]]` is a syntax error, which `_step_links.py` records
 * — so a fork bears no sentinel to resolve. `swimlane` was absent for no reason: the renderer emits
 * `|[[arch://author Author]]|` and PlantUML renders a real anchor, but an unbound lane's sentinel is
 * its own local id, and without the lane's type here that id resolved to nothing and the anchor was
 * skipped. The header was a link that selected nothing.
 */
const _SENTINEL_BEARING_TYPES = new Set(['swimlane', 'action', 'decision', 'partition'])
const _SENTINEL_PREFIX = 'arch://'

/**
 * Maps a sentinel value (either a bound entity's own artifact id, or a diagram-local step's
 * local id — see `_step_links.py`'s `sentinel_target`) to the artifact id the frontend should
 * select. A bound sentinel already IS the target artifact id; an unbound one is looked up by
 * the diagram-local placeholder entity's `display_alias` (`extract_diagram_entities` sets it
 * to the element's own local id), scoped to the types that bear a sentinel so a local id cannot
 * collide with something else's alias.
 */
type SentinelTarget = { artifactId: string; artifactType: string }

function buildSentinelIndex(entities: DiagramMapContext['entities']): Map<string, SentinelTarget> {
  const index = new Map<string, SentinelTarget>()
  for (const e of entities) {
    const target: SentinelTarget = { artifactId: e.artifact_id, artifactType: e.artifact_type }
    index.set(e.artifact_id, target)
    if (_SENTINEL_BEARING_TYPES.has(e.artifact_type) && e.display_alias) {
      index.set(e.display_alias, target)
    }
  }
  return index
}

/**
 * A lane header is a label in the lane band and has no shape of its own, so the shape-then-label
 * pairing below does not describe it. Measured on a real three-lane render: the first lane's anchor
 * happens to follow a `<polygon>` belonging to the content above it, so pairing would have adopted an
 * unrelated element and highlighted it whenever the lane was selected. The later two follow `<text>`
 * and would have paired with nothing — the same header behaving two ways in one diagram.
 */
const _TYPES_WITHOUT_A_SHAPE = new Set(['swimlane'])

const _SHAPE_TAGS = new Set(['rect', 'polygon'])

/**
 * The step's shape element, if the SVG structure allows finding it: PlantUML emits the
 * action `<rect>` / decision `<polygon>` as the immediate previous sibling of the label's
 * sentinel `<a>`. Anything else in that position (an arrow path, another label) means the
 * structure isn't the expected shape-then-label pair — return null rather than guess.
 */
function stepShapeFor(a: SVGAElement): Element | null {
  const prev = a.previousElementSibling
  return prev && _SHAPE_TAGS.has(prev.tagName.toLowerCase()) ? prev : null
}

/**
 * Activity diagrams: PlantUML's activity syntax gives fork no label/link position at all
 * (unselectable — see `_step_links.py`), and provides no `<g>` per step. The sentinel
 * `[[arch://…]]` link wraps the step's label (see `sentinel_wrapped`), so the `<a>` plus —
 * when structurally identifiable — the step's shape element (the rect/polygon PlantUML emits
 * immediately before the label) are the selectable, highlightable elements: clicking anywhere
 * on the step selects it, not only the label text.
 */
export function activityMapElements(svgRoot: SVGSVGElement, ctx: DiagramMapContext): DiagramElementMap {
  const nodes = new Map<string, Element[]>()
  const sentinelIndex = buildSentinelIndex(ctx.entities)

  for (const a of Array.from(svgRoot.querySelectorAll<SVGAElement>('a'))) {
    const href = a.getAttribute('href') ?? ''
    if (!href.startsWith(_SENTINEL_PREFIX)) continue
    const target = sentinelIndex.get(href.slice(_SENTINEL_PREFIX.length))
    if (!target) continue
    const elements = nodes.get(target.artifactId) ?? []
    const shape = _TYPES_WITHOUT_A_SHAPE.has(target.artifactType) ? null : stepShapeFor(a)
    if (shape) elements.push(shape)
    elements.push(a)
    nodes.set(target.artifactId, elements)
  }

  return { nodes, edges: new Map() }
}
