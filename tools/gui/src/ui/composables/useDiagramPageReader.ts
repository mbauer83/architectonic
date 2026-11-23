import { computed, type Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext } from '../../domain'
import type { ReachedRow } from '../../domain/diagramReadingLists'
import type { ShowToast } from '../keys'
import type { useDiagramSvgSelection } from './useDiagramSvgSelection'
import type { useFittedPanZoom } from './useFittedPanZoom'
import { useDiagramReader } from './useDiagramReader'
import { useReadingAddress } from './useReadingAddress'
import { useReadingKeyboard } from './useReadingKeyboard'

/**
 * The diagram reader as the diagram page mounts it: the reading (`useDiagramReader`), its address
 * (`useReadingAddress`) and its keyboard (`useReadingKeyboard`), joined to the page's selection and
 * window, and the Reading panel's rows. One call, so the page holds the wiring in one line rather than
 * the three composables' plumbing.
 */
export function useDiagramPageReader(options: {
  svc: Pick<ModelService, 'getDiagramTypeConnectionTypes' | 'getDerivedNeighbors'>
  route: RouteLocationNormalizedLoaded
  router: Router
  context: Ref<DiagramContext | null>
  /** View mode with the picture drawn: the only time there is a reading. */
  viewing: Ref<boolean>
  selection: ReturnType<typeof useDiagramSvgSelection>
  panZoom: ReturnType<typeof useFittedPanZoom>
  host: Ref<HTMLElement | null>
  toast: ShowToast
}) {
  const { context, selection, panZoom } = options
  const reader = useDiagramReader({ svc: options.svc, context, viewing: options.viewing, selection })
  const entityById = computed(() =>
    new Map((context.value?.entities ?? []).map((entity) => [entity.artifact_id, entity])))
  const select = (ids: readonly string[]) => {
    if (ids.length === 0) { selection.clearSelection(); return }
    selection.selectEntity(ids[0])
    for (const id of ids.slice(1)) selection.selectEntity(id, true)
  }

  const frame = () => { const extent = reader.readingExtent(); if (extent) panZoom.frame(extent) }
  const address = useReadingAddress({
    route: options.route, router: options.router,
    ready: computed(() => options.viewing.value && selection.nodeElements.value.size > 0),
    selectedIds: selection.selectedIds, drawnIds: () => [...entityById.value.keys()], reach: reader.reach, select,
    window: {
      moved: panZoom.isTransformed, current: panZoom.windowView, show: panZoom.showView, reset: panZoom.resetView,
      changes: () => [panZoom.scale.value, panZoom.tx.value, panZoom.ty.value],
    },
  })
  const keyboard = useReadingKeyboard({
    host: options.host, nodeElements: selection.nodeElements, selectedIds: selection.selectedIds,
    describe: (id) => {
      const entity = entityById.value.get(id)
      return entity ? { name: entity.name, type: entity.artifact_type.replace(/-/g, ' ') } : null
    },
    select: (id, additive) => selection.selectEntity(id, additive),
    clear: selection.clearSelection, frame, reveal: panZoom.reveal, enabled: options.viewing,
  })

  const rowOf = (id: string): ReachedRow[] => {
    const entity = entityById.value.get(id)
    return entity ? [{ id, name: entity.name, type: entity.artifact_type, domain: entity.domain }] : []
  }
  const panel = computed(() => {
    const focus = reader.focus.value
    return {
      title: focus.length === 1 ? (entityById.value.get(focus[0])?.name ?? focus[0]) : `${focus.length} elements`,
      reach: reader.reach.value, flowOn: reader.flowOn.value, reducedMotion: reader.reducedMotion.value,
      drawn: {
        incoming: reader.reached.value.incoming.flatMap(rowOf), outgoing: reader.reached.value.outgoing.flatMap(rowOf),
      },
      notDrawn: reader.notDrawn.value, derived: reader.derived.value,
    }
  })

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(address.link())
      options.toast('Link to this reading copied: selection, reach and window.')
    } catch {
      options.toast('The link could not be copied; the address bar holds it.', 'error')
    }
  }

  /** The canvas is one `Tab` stop in view mode, named for what it holds and how to go in. */
  const hostAttributes = computed(() => (options.viewing.value
    ? {
      tabindex: 0,
      'aria-label': `Diagram ${context.value?.diagram.name ?? ''}: Enter or an arrow key reaches its elements`,
    }
    : {}))

  return {
    reading: reader.reading, panel, hostAttributes, onKeydown: keyboard.onKeydown,
    /** What the Reading panel asks for, by its event names. */
    panelEvents: {
      'update:reach': (reach: typeof reader.reach.value) => { reader.reach.value = reach },
      'toggle-flow': reader.toggleFlow,
      frame,
      'copy-link': copyLink,
      clear: () => selection.clearSelection(),
      select: (id: string) => select([id]),
      hover: (id: string | null) => selection.setHovered(id),
    },
  }
}
