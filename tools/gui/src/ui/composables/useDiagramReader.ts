import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { Effect, Exit } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext } from '../../domain'
import type { DerivedNeighbor } from '../../domain/schemas/entities'
import type { Extent } from '../../domain/layout/geometry'
import { DEFAULT_REACH, reachOf, type Reach, type ReadingRelation } from '../../domain/diagramReading'
import { derivedOf, notDrawnOf } from '../../domain/diagramReadingLists'
import { unionOf } from '../../domain/layout/lab/labArrangement'
import { paintReading, type FlowOf } from '../lib/diagramReadingPaint'
import { pictureExtentOf } from '../lib/svgExtent'
import { onReducedMotionChange, readerPrefersReducedMotion } from '../lib/motionPreference'

/** What the reader needs of the picture's selection: the selected entities and what everything is drawn as. */
export interface ReaderSelection {
  readonly selectedIds: Ref<readonly string[]>
  readonly nodeElements: Ref<ReadonlyMap<string, readonly Element[]>>
  readonly edgeElements: Ref<ReadonlyMap<string, readonly Element[]>>
  readonly svgContainer: Ref<HTMLElement | null>
}

/** The flow toggle is remembered per browser: a reader who wants it on wants it on everywhere. */
const FLOW_KEY = 'arch_diagram_reading_flow'
const remembered = (): boolean => { try { return localStorage.getItem(FLOW_KEY) === '1' } catch { return false } }
const remember = (on: boolean): void => {
  try { localStorage.setItem(FLOW_KEY, on ? '1' : '0') } catch { /* storage refused: remembered for this page only */ }
}

/**
 * The diagram reader (B97) on a diagram page in view mode: select, and the rest steps back.
 *
 * The selection is the picture's own (`useDiagramSvgSelection`); this adds what it reaches along the
 * drawn relations — `reachOf` walks them, incoming and outgoing as far as the reach says — marks the
 * picture (`paintReading`), and lists what the picture leaves out: the model's relations for the
 * selection that are not drawn, and the relationships the model derives through other elements.
 *
 * Only in view mode. In edit mode a selection means "this is what I am arranging", and nothing dims.
 */
export function useDiagramReader(options: {
  svc: Pick<ModelService, 'getDiagramTypeConnectionTypes' | 'getDerivedNeighbors'>
  context: Ref<DiagramContext | null>
  /** Whether the page is in view mode with its picture drawn. */
  viewing: Ref<boolean>
  selection: ReaderSelection
}) {
  const { svc, context, viewing, selection } = options
  const reach = ref<Reach>(DEFAULT_REACH)
  const flowOn = ref(remembered())
  const reducedMotion = ref(readerPrefersReducedMotion())
  onUnmounted(onReducedMotionChange((reduced) => { reducedMotion.value = reduced }))

  const focus = computed(() => (viewing.value ? selection.selectedIds.value : []))
  const reading = computed(() => focus.value.length > 0)

  // The diagram type's connection catalogue says which types have no direction (`symmetric`).
  const undirected = ref<ReadonlySet<string>>(new Set())
  watch(() => context.value?.diagram.diagram_type, async (diagramType) => {
    if (!diagramType) return
    const exit = await Effect.runPromiseExit(svc.getDiagramTypeConnectionTypes(diagramType))
    if (Exit.isFailure(exit)) return
    undirected.value = new Set(exit.value.flatMap((item) =>
      (item.symmetric === true && typeof item.connection_type === 'string' ? [item.connection_type] : [])))
  }, { immediate: true })

  const relations = computed((): ReadingRelation[] => (context.value?.connections ?? []).map((connection) => ({
    id: connection.artifact_id, source: connection.source, target: connection.target,
    directed: !undirected.value.has(connection.conn_type),
  })))
  const reached = computed(() => reachOf(focus.value, relations.value, reach.value))

  const notDrawn = computed(() => notDrawnOf({
    selection: focus.value,
    candidates: context.value?.candidate_connections ?? [],
    drawnRelations: new Set(relations.value.map((relation) => relation.id)),
    drawnEntities: new Set((context.value?.entities ?? []).map((entity) => entity.artifact_id)),
    undirected: undirected.value,
    reach: reach.value,
  }))

  // Derived relationships, read once per selected element and kept while the page shows the diagram.
  const derivedById = ref(new Map<string, readonly DerivedNeighbor[] | 'loading' | 'failed'>())
  watch(focus, (ids) => {
    for (const id of ids) {
      if (derivedById.value.has(id)) continue
      derivedById.value.set(id, 'loading')
      void Effect.runPromiseExit(svc.getDerivedNeighbors(id)).then((exit) => {
        derivedById.value.set(id, Exit.isSuccess(exit) ? exit.value : 'failed')
      })
    }
  })
  watch(() => context.value?.diagram.artifact_id, () => { derivedById.value = new Map() })
  const derived = computed(() => {
    const states = focus.value.map((id) => derivedById.value.get(id))
    const loaded = new Map(focus.value.flatMap((id, index) => {
      const state = states[index]
      return Array.isArray(state) ? [[id, state]] : []
    }))
    return {
      ...derivedOf(loaded, reach.value, undirected.value),
      loading: states.some((state) => state === 'loading' || state === undefined),
      failed: states.some((state) => state === 'failed'),
    }
  })

  const flowing = computed(() => flowOn.value && reading.value)
  watch([reached, reading, flowing, selection.nodeElements, selection.edgeElements], () => {
    const svg = selection.svgContainer.value?.querySelector('svg')
    if (!svg) return
    if (!reading.value) { paintReading(svg, selection.nodeElements.value, selection.edgeElements.value, null); return }
    const lit = new Set([...focus.value, ...reached.value.incoming, ...reached.value.outgoing])
    const flow = flowing.value ? new Map([...reached.value.relations].flatMap((id): [string, FlowOf][] => {
      const relation = relations.value.find((one) => one.id === id)
      return relation
        ? [[id, { directed: relation.directed, target: selection.nodeElements.value.get(relation.target) ?? [] }]]
        : []
    })) : null
    const paint = { lit, relations: reached.value.relations, flow }
    paintReading(svg, selection.nodeElements.value, selection.edgeElements.value, paint)
  }, { flush: 'post' })

  /** The part of the picture the reading covers: the selection and what it reaches. */
  const readingExtent = (): Extent | null => {
    const ids = [...focus.value, ...reached.value.incoming, ...reached.value.outgoing]
    const extents = ids.flatMap((id) => selection.nodeElements.value.get(id) ?? [])
      .flatMap((element) => pictureExtentOf(element) ?? [])
      .filter((extent) => extent.right > extent.left || extent.bottom > extent.top)
    return extents.length > 0 ? unionOf(extents) : null
  }

  return {
    reach, reading, focus, reached, notDrawn, derived, readingExtent,
    flowOn: computed(() => flowOn.value),
    reducedMotion: computed(() => reducedMotion.value),
    /** Latch the flow on or off. Unavailable under reduced motion, where the arrowheads carry direction. */
    toggleFlow: () => {
      if (reducedMotion.value) return
      flowOn.value = !flowOn.value
      remember(flowOn.value)
    },
  }
}
