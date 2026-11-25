/**
 * The scope of the architecture under evaluation (06·0): from a diagram (the whole of it, or the
 * elements pressed on its canvas), a viewpoint, or a search with tick boxes — always a set of entity ids.
 *
 * What the canvas draws it on (Q36): the chosen diagram; for a viewpoint, a stored diagram that applies
 * it; otherwise — a viewpoint no stored diagram applies, or a search — a view generated from the scope.
 * The naive candidate is drawn on the same stored diagram (`drawnOn`), so the workspace opens on the
 * picture the start previewed. What the stored picture draws outside the scope steps back.
 */
import { computed, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext, DiagramSummary, SearchHit, ViewpointDefinitionEnvelope } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { formatEffectError } from '../lib/errors'

export type ScopeSource = 'diagram' | 'viewpoint' | 'search'

/** Above this many elements a scope is large enough to say so. */
export const LARGE_SCOPE = 150
/** How long the ticks of a search settle before the generated view is drawn again. */
const DRAW_AFTER_MS = 400

/** The diagrams and viewpoints the scope is chosen among, as the start page lists them. */
export interface ScopeChoices {
  readonly diagrams: () => readonly DiagramSummary[]
  readonly viewpoints: () => readonly ViewpointDefinitionEnvelope[]
}

/** What choosing and drawing a scope reads through: the model service's diagram, viewpoint and search half. */
export type ScopeAccess = Pick<ModelService,
  'getDiagramContext' | 'readLayoutGeometry' | 'drawScope' | 'executeViewpoint' | 'getViewpointReferencers' | 'search'>

export function useAnalysisScope(svc: ScopeAccess, choices: ScopeChoices) {
  const source = ref<ScopeSource>('diagram')
  const diagramId = ref('')
  const wholeDiagram = ref(true)
  const pressed = ref<ReadonlySet<string>>(new Set())
  const viewpoint = ref('')
  const viewpointIds = ref<readonly string[]>([])
  /** A stored diagram that applies the chosen viewpoint, or empty where none does. */
  const applying = ref('')
  const query = ref('')
  const searched = ref('')
  const hits = shallowRef<readonly SearchHit[]>([])
  const ticked = ref<ReadonlySet<string>>(new Set())
  const context = shallowRef<DiagramContext | null>(null)
  const drawing = shallowRef<LayoutGeometry | null>(null)
  const drawingBusy = ref(false)
  const error = ref<string | null>(null)

  /** The stored diagram the scope is drawn on; empty where it is drawn as a generated view. */
  const drawnOn = computed(() => ({ diagram: diagramId.value, viewpoint: applying.value, search: '' })[source.value])

  const drawnIds = computed(() => (context.value?.entities ?? []).map((one) => one.artifact_id))

  /** The scope, as entity ids. */
  const ids = computed((): readonly string[] => {
    if (source.value === 'search') return [...ticked.value]
    if (source.value === 'viewpoint') return viewpointIds.value
    return wholeDiagram.value ? drawnIds.value : drawnIds.value.filter((id) => pressed.value.has(stableEntityId(id)))
  })
  /** What the stored picture draws that the scope leaves out, by stable id. */
  const outside = computed((): ReadonlySet<string> => {
    const inside = new Set(ids.value.map(stableEntityId))
    return new Set(drawnIds.value.map(stableEntityId).filter((id) => !inside.has(id)))
  })

  /** What the scope is of, in words: the diagram, the viewpoint or the search it was chosen by. */
  const subject = computed((): string => {
    if (source.value === 'search') return searched.value ? `search “${searched.value}”` : ''
    const named = choices.viewpoints().find((one) => one.slug === viewpoint.value)
    if (source.value === 'viewpoint') return named?.name ?? ''
    return choices.diagrams().find((one) => one.artifact_id === diagramId.value)?.name ?? ''
  })

  const failed = (failure: unknown): void => {
    error.value = formatEffectError(failure)
  }

  watch(drawnOn, async (id) => {
    context.value = null
    drawing.value = null
    pressed.value = new Set()
    if (!id) return
    try {
      const [read, picture] = await Promise.all([
        Effect.runPromise(svc.getDiagramContext(id)), Effect.runPromise(svc.readLayoutGeometry(id)),
      ])
      if (drawnOn.value !== id) return
      context.value = read
      drawing.value = picture
    } catch (failure) {
      failed(failure)
    }
  })

  /** A scope no stored diagram draws is drawn as a generated view, once its ids settle. */
  let pending: ReturnType<typeof setTimeout> | undefined
  const drawGenerated = async (scope: readonly string[], name: string): Promise<void> => {
    drawingBusy.value = true
    try {
      const picture = await Effect.runPromise(svc.drawScope(scope, name || 'The scope'))
      if (!drawnOn.value && ids.value === scope) drawing.value = picture
    } catch (failure) {
      failed(failure)
    } finally {
      drawingBusy.value = false
    }
  }
  watch([drawnOn, ids], ([on, scope]) => {
    clearTimeout(pending)
    if (on) return
    drawing.value = null
    if (scope.length > 0) pending = setTimeout(() => { void drawGenerated(scope, subject.value) }, DRAW_AFTER_MS)
  })

  /** A press on the canvas while choosing elements: in the scope, or out again. */
  const press = (stableId: string) => {
    if (source.value !== 'diagram' || wholeDiagram.value) return
    const next = new Set(pressed.value)
    if (!next.delete(stableId)) next.add(stableId)
    pressed.value = next
  }

  /** What a reader of the scope chooses: how it is chosen, the diagram, all of it or the pressed, what is searched. */
  const choose = {
    source: (next: ScopeSource) => { source.value = next },
    diagram: (id: string) => { diagramId.value = id },
    whole: (whole: boolean) => { wholeDiagram.value = whole },
    query: (text: string) => { query.value = text },
  }

  /** The viewpoint's population, and a stored diagram that applies it, if there is one. */
  const runViewpoint = async (slug: string) => {
    viewpoint.value = slug
    viewpointIds.value = []
    applying.value = ''
    if (!slug) return
    try {
      const [result, referencers] = await Promise.all([
        Effect.runPromise(svc.executeViewpoint({ slug })), Effect.runPromise(svc.getViewpointReferencers(slug)),
      ])
      const drawable = new Set(choices.diagrams().map((one) => one.artifact_id))
      viewpointIds.value = result.entity_ids
      applying.value = referencers.find((one) => one.target_kind === 'diagram' && drawable.has(one.artifact_id))
        ?.artifact_id ?? ''
    } catch (failure) {
      failed(failure)
    }
  }

  const search = async () => {
    try {
      const result = await Effect.runPromise(svc.search(query.value.trim(), 40))
      searched.value = query.value.trim()
      hits.value = result.hits.filter((hit) => hit.record_type === 'entity')
    } catch (failure) {
      failed(failure)
    }
  }
  const tick = (id: string) => {
    const next = new Set(ticked.value)
    if (!next.delete(id)) next.add(id)
    ticked.value = next
  }

  return {
    source, diagramId, wholeDiagram, pressed, viewpoint, viewpointIds, query, hits, ticked, context, drawing,
    drawingBusy, error, drawnOn, ids, outside, subject, choose, press, runViewpoint, search, tick,
  }
}

export type AnalysisScope = ReturnType<typeof useAnalysisScope>
