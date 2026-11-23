/**
 * Step 1 of starting an analysis (06·0): the scope, from a diagram (the whole of it, or the elements
 * pressed on its canvas), a viewpoint, or a search with tick boxes — always a set of entity ids. The
 * diagram, where there is one, is what the canvas previews and what the analysis records as its scope
 * diagram; what lies outside the scope steps back.
 */
import { computed, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext, SearchHit } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { formatEffectError } from '../lib/errors'

export type ScopeSource = 'diagram' | 'viewpoint' | 'search'

/** Above this many elements a scope is large enough to say so. */
export const LARGE_SCOPE = 150

export function useAnalysisScope(svc: ModelService) {
  const source = ref<ScopeSource>('diagram')
  const diagramId = ref('')
  const wholeDiagram = ref(true)
  const pressed = ref<ReadonlySet<string>>(new Set())
  const context = shallowRef<DiagramContext | null>(null)
  const drawing = shallowRef<LayoutGeometry | null>(null)
  const viewpointIds = ref<readonly string[]>([])
  const query = ref('')
  const hits = shallowRef<readonly SearchHit[]>([])
  const ticked = ref<ReadonlySet<string>>(new Set())
  const error = ref<string | null>(null)

  watch(diagramId, async (id) => {
    context.value = null
    drawing.value = null
    pressed.value = new Set()
    if (!id) return
    try {
      const [read, picture] = await Promise.all([
        Effect.runPromise(svc.getDiagramContext(id)), Effect.runPromise(svc.readLayoutGeometry(id)),
      ])
      if (diagramId.value !== id) return
      context.value = read
      drawing.value = picture
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  })

  const drawnIds = computed(() => (context.value?.entities ?? []).map((one) => one.artifact_id))

  /** The scope, as entity ids. */
  const ids = computed((): readonly string[] => {
    if (source.value === 'search') return [...ticked.value]
    if (source.value === 'viewpoint') return viewpointIds.value
    return wholeDiagram.value ? drawnIds.value : drawnIds.value.filter((id) => pressed.value.has(stableEntityId(id)))
  })
  /** What the canvas draws that the scope leaves out, by stable id. */
  const outside = computed((): ReadonlySet<string> => {
    const inside = new Set(ids.value.map(stableEntityId))
    return new Set(drawnIds.value.map(stableEntityId).filter((id) => !inside.has(id)))
  })

  /** A press on the canvas while choosing elements: in the scope, or out again. */
  const press = (stableId: string) => {
    if (source.value !== 'diagram' || wholeDiagram.value) return
    const next = new Set(pressed.value)
    if (!next.delete(stableId)) next.add(stableId)
    pressed.value = next
  }

  const runViewpoint = async (slug: string) => {
    try {
      const result = await Effect.runPromise(svc.executeViewpoint({ slug }))
      viewpointIds.value = result.entity_ids
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }

  const search = async () => {
    try {
      const result = await Effect.runPromise(svc.search(query.value.trim(), 40))
      hits.value = result.hits.filter((hit) => hit.record_type === 'entity')
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }
  const tick = (id: string) => {
    const next = new Set(ticked.value)
    if (!next.delete(id)) next.add(id)
    ticked.value = next
  }

  return {
    source, diagramId, wholeDiagram, pressed, context, drawing, viewpointIds, query, hits, ticked, error,
    ids, outside, press, runViewpoint, search, tick,
  }
}

export type AnalysisScope = ReturnType<typeof useAnalysisScope>
