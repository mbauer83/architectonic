import type { DiagramMapContext, DiagramElementMap } from '../../lib/diagramViewerExtensions'

/** A step's attached note as stored in the diagram-entities payload. */
export type StepNote = { side: string; text: string }

const _SENTINEL_STEP_TYPES = new Set(['action', 'decision', 'partition'])
const _SENTINEL_PREFIX = 'arch://'

/**
 * Maps a sentinel value (either a bound entity's own artifact id, or a diagram-local step's
 * local id — see `_step_links.py`'s `sentinel_target`) to the artifact id the frontend should
 * select. A bound sentinel already IS the target artifact id; an unbound one is looked up by
 * the diagram-local placeholder entity's `display_alias` (`extract_diagram_entities` sets it
 * to the step's own local id), scoped to step entity types to avoid an accidental collision.
 */
function buildSentinelIndex(entities: DiagramMapContext['entities']): Map<string, string> {
  const index = new Map<string, string>()
  for (const e of entities) {
    index.set(e.artifact_id, e.artifact_id)
    if (_SENTINEL_STEP_TYPES.has(e.artifact_type) && e.display_alias) {
      index.set(e.display_alias, e.artifact_id)
    }
  }
  return index
}

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
    const artifactId = sentinelIndex.get(href.slice(_SENTINEL_PREFIX.length))
    if (!artifactId) continue
    const elements = nodes.get(artifactId) ?? []
    const shape = stepShapeFor(a)
    if (shape) elements.push(shape)
    elements.push(a)
    nodes.set(artifactId, elements)
  }

  return { nodes, edges: new Map() }
}
