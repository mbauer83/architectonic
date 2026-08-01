import { watch, type Ref } from 'vue'
import type { DiagramConnection, DiagramViewpointProjection, DiagramContextEntity } from '../../domain'
import { resolveElementMap, neutralizeSentinelLink } from '../lib/diagramViewerExtensions'
import { reasonHint, effectiveOcclusionState, projectionByItemId } from '../views/EditDiagramView.helpers'

/**
 * Wires click-to-toggle interactivity into the diagram-edit view's rendered SVG (click an
 * entity to mark it for removal, click a connection to toggle it) and applies the
 * removal/viewpoint-ghost overlay classes. Re-attaches whenever the SVG, entity/connection
 * lists, or diagram-type-owned entity data change; re-applies highlight classes whenever
 * the removal/addition selection or the viewpoint projection changes.
 */
export function useDiagramEditSvgOverlay(options: {
  svgHtml: Ref<string | null>
  diagramType: Ref<string | undefined>
  diagramEntities: Ref<DiagramContextEntity[]>
  diagramConnections: Ref<DiagramConnection[]>
  typeEntityData: Ref<Record<string, unknown>>
  toRemoveEntityIds: Ref<Set<string>>
  toRemoveConnIds: Ref<Set<string>>
  selectedNewConnIds: Ref<Set<string>>
  isConnIncluded: (connId: string) => boolean
  includedConnIds: Ref<Set<string>>
  viewpointProjection: Ref<DiagramViewpointProjection | null>
  hideInsteadOfGhost: Ref<boolean>
  toggleEntityRemoval: (id: string) => void
  toggleConn: (connId: string) => void
  /** The element holding the rendered SVG, owned by the caller's template. */
  svgContainer: Readonly<Ref<HTMLElement | null>>
}) {
  const {
    svgHtml, diagramType, diagramEntities, diagramConnections, typeEntityData,
    toRemoveEntityIds, toRemoveConnIds, selectedNewConnIds, isConnIncluded, includedConnIds,
    viewpointProjection, hideInsteadOfGhost, toggleEntityRemoval, toggleConn, svgContainer,
  } = options

  const svgEntityElems = new Map<string, Element[]>()
  const svgConnElems = new Map<string, Element[]>()

  const applyViewpointOverlay = (id: string, elems: Element[]) => {
    const occurrence = projectionByItemId(viewpointProjection.value).get(id)
    const state = occurrence ? effectiveOcclusionState(occurrence, hideInsteadOfGhost.value) : 'visible'
    const hint = occurrence ? reasonHint(occurrence.reasons) : null
    for (const el of elems) {
      el.classList.toggle('svg-viewpoint-ghosted', state === 'ghosted')
      el.classList.toggle('svg-viewpoint-hidden', state === 'hidden')
      if (hint) el.setAttribute('title', hint)
      else el.removeAttribute('title')
    }
  }

  const updateHighlights = () => {
    for (const [id, elems] of svgEntityElems) {
      for (const el of elems) el.classList.toggle('svg-remove', toRemoveEntityIds.value.has(id))
      applyViewpointOverlay(id, elems)
    }
    for (const [id, elems] of svgConnElems) {
      const excl = !isConnIncluded(id) && includedConnIds.value.has(id)
      for (const el of elems) el.classList.toggle('svg-remove', excl)
      applyViewpointOverlay(id, elems)
    }
  }

  const attachInteractivity = () => {
    svgEntityElems.clear(); svgConnElems.clear()
    const svgEl = svgContainer.value?.querySelector('svg')
    if (!svgEl || !diagramEntities.value.length) return

    const { nodes, edges } = resolveElementMap(diagramType.value, svgEl, {
      entities: diagramEntities.value,
      connections: diagramConnections.value,
      diagramEntities: typeEntityData.value,
    })
    for (const [artifactId, elems] of nodes) {
      svgEntityElems.set(artifactId, elems)
      for (const el of elems) {
        if (!(el instanceof SVGElement)) continue
        el.setAttribute('data-entity-id', artifactId)
        el.addEventListener('click', (ev) => { ev.stopPropagation(); ev.preventDefault(); toggleEntityRemoval(artifactId) })
        if (el instanceof SVGAElement) neutralizeSentinelLink(el)
      }
    }
    for (const [connArtifactId, elems] of edges) {
      // Registered for the same reason entities are: updateHighlights() drives the
      // marked-for-removal styling off these maps. Wiring only the click handler leaves a
      // connection that toggles its removal state with nothing to show for it — the click
      // registers, the diagram looks unchanged, and the edit appears not to have happened.
      svgConnElems.set(connArtifactId, elems)
      for (const el of elems) {
        if (!(el instanceof SVGElement)) continue
        el.setAttribute('data-conn-id', connArtifactId)
        el.addEventListener('click', (ev) => { ev.stopPropagation(); ev.preventDefault(); toggleConn(connArtifactId) })
        if (el instanceof SVGAElement) neutralizeSentinelLink(el)
      }
    }
    updateHighlights()
  }

  watch([svgHtml, diagramEntities, diagramConnections, typeEntityData], attachInteractivity, { flush: 'post' })
  watch([toRemoveEntityIds, toRemoveConnIds, selectedNewConnIds], updateHighlights)
  watch([viewpointProjection, hideInsteadOfGhost], updateHighlights)
}
