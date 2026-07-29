import type { Component } from 'vue'
import type { DiagramConnection, EntitySummary } from '../../domain'
import { graphvizMapElements } from './graphvizElementMapping'

/**
 * Viewer-side diagram-type extension registry.
 *
 * Mirrors `diagramAuthoringExtensions` but for the read-only diagram viewer: a diagram type
 * may contribute selectable *sub-parts* of an entity node (e.g. a classifier's attribute rows)
 * plus a sidebar panel that renders the selected sub-part's detail. This keeps all diagram-type
 * knowledge inside `ui/diagram-types/<type>/`; the generic viewer only knows "a type may make
 * node sub-parts selectable and supply a detail component", never what a classifier or an
 * attribute is.
 */
export interface ViewerSubPartContext {
  /** Resolved entity id of the node (its `data-entity-id`). */
  entityId: string
  /** The SVG `<g>` element for this entity. */
  node: SVGGElement
  /** Raw `diagram-entities` frontmatter — shape is owned by the diagram type. */
  diagramEntities: Record<string, unknown>
  /** Aborted when interactivity is re-attached; use to scope event listeners. */
  signal: AbortSignal
  /**
   * Select a sub-part. `detail` is opaque to the viewer and handed to `detailComponent` as
   * `detail`. `elements` are the SVG nodes that make up the sub-part (e.g. an attribute row's
   * glyph and label); the viewer toggles a generic selected-highlight class on them.
   */
  onSelect: (detail: unknown, elements?: Element[]) => void
}

/** Inputs a `mapElements` implementation needs to resolve SVG elements to model artifacts. */
export interface DiagramMapContext {
  entities: ReadonlyArray<EntitySummary>
  connections: ReadonlyArray<DiagramConnection>
  /**
   * Raw `diagram-entities` frontmatter, for types whose renderer gives no per-element SVG
   * anchor and must instead match DOM order against the authored array order (e.g. sequence
   * messages). Omitted by default — only extensions that need authored order read it.
   */
  diagramEntities?: Record<string, unknown>
}

/**
 * SVG-element↔artifact mapping for a rendered diagram. One-to-many from the start: an
 * artifact_id key may resolve to several SVG elements (a model entity occurring more than once
 * in one view — see WU-B3). Selection highlights every mapped element; clicking any of them
 * selects the artifact.
 */
export interface DiagramElementMap {
  nodes: Map<string, Element[]>
  edges: Map<string, Element[]>
}

export interface DiagramViewerExtension {
  /** Attach click handlers to selectable sub-parts within an entity node. */
  attachNodeSubParts: (ctx: ViewerSubPartContext) => void
  /** Sidebar component for a selected sub-part. Receives `detail` (the `onSelect` payload); emits `close`. */
  detailComponent: Component
  /**
   * Optional sidebar section rendered inside the generic selected-entity panel for this diagram
   * type — the modular home for diagram-type-specific entity meta-information (e.g. a datatype
   * classifier's role/provenance/note/tags), so the generic sidebar never learns what a classifier
   * is. Receives `{ entity, entityId }`; emits `save` with an opaque metadata patch the view
   * persists. Omitted by types that add nothing to the generic panel.
   */
  entityDetailSection?: Component
  /**
   * Map this diagram type's rendered SVG to artifact ids. Optional — types whose SVG follows
   * graphviz/PlantUML's default id/attribute conventions omit it; the generic viewer then falls
   * back to `graphvizMapElements`, which becomes the default implementation of this contract
   * rather than special-cased logic inside the view.
   */
  mapElements?: (svgRoot: SVGSVGElement, ctx: DiagramMapContext) => DiagramElementMap
}

const registry = new Map<string, DiagramViewerExtension>()

export const registerViewerExtension = (diagramType: string, ext: DiagramViewerExtension): void => {
  registry.set(diagramType, ext)
}

export const lookupViewerExtension = (
  diagramType: string | null | undefined,
): DiagramViewerExtension | undefined => (diagramType ? registry.get(diagramType) : undefined)

/**
 * Resolve the element map for a diagram: the registered extension's `mapElements` if it
 * declares one, otherwise the graphviz/PlantUML default matcher.
 */
export const resolveElementMap = (
  diagramType: string | null | undefined,
  svgRoot: SVGSVGElement,
  ctx: DiagramMapContext,
): DiagramElementMap => {
  const ext = lookupViewerExtension(diagramType)
  return ext?.mapElements ? ext.mapElements(svgRoot, ctx) : graphvizMapElements(svgRoot, ctx)
}

/**
 * Some `mapElements` implementations (e.g. activity's sentinel `[[arch://…]]` links) return a
 * real `<a>` as the selectable representative. Once the viewer has read its `href` to build the
 * map and attached its own click listener, the anchor's native navigation must be disarmed —
 * `preventDefault` alone only covers a plain left-click; a middle-click/new-tab or drag-to-bookmark
 * bypasses the `click` handler entirely and would try to launch the unregistered `arch:` scheme.
 */
export const neutralizeSentinelLink = (a: SVGAElement): void => {
  a.removeAttribute('href')
  a.removeAttributeNS('http://www.w3.org/1999/xlink', 'href')
  a.removeAttribute('target')
}
