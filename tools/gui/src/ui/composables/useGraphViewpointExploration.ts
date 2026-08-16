import { Effect } from 'effect'
import { computed, ref, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ModelService } from '../../application/ModelService'
import type { ViewpointDefinitionEnvelope, ViewpointSummary } from '../../domain'
import type { PresentationNode } from '../../domain/viewpointPresentation'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import {
  computeExecutionDiagnostics, deriveLegend, deriveScaleGradients,
} from '../components/ViewpointExecutionDiagnostics.helpers'
import type { AdHocExecution } from '../lib/adHocExecution'
import type { ParameterDraft } from '../lib/viewpointExecutionParameters'
import { viewpointSummaryFromEnvelope } from '../lib/viewpointSummary'
import { VERIFIED_KEYS, executionQuery, parametersFromQuery } from '../lib/viewpointUrlState'
import {
  buildConnectionStyleIndex, buildConnectionSummaryIndex, explorationRedirectFor, projectionByItemId,
} from '../views/GraphExploreView.helpers'
import { useViewpointExecution } from './useViewpointExecution'
import { useViewpointParameterPrompt, type ResolvedViewpointExecution } from './useViewpointParameterPrompt'

/** What the exploration surface does with a population; supplied by the view that owns the graph. */
interface ViewpointExplorationActions {
  /** Empty the graph and drop the selection, before a new population replaces it. */
  clearGraph: () => void
  /** Draw the execution's result. What that takes — resetting expansion, resolving domains,
   *  laying out — belongs to whoever owns the graph, so it is one action from here. */
  populate: () => void
  /** Restore free exploration from the route's entity, once no viewpoint is selected. */
  loadRoot: () => void
}

/**
 * The graph explorer's viewpoint half: the catalog it picks from, the execution it runs, and
 * everything a result is read through — presentation, per-item styling, diagnostics, legends.
 *
 * Lifted out of `GraphExploreView.vue` rather than written beside it — the view had grown past
 * the file-length policy and this was the self-contained half. It owns the address as state for
 * the viewpoint keys (`viewpoint`, `param.*`, and the verification pins that survive a
 * same-viewpoint re-run) and owns nothing about the graph: populating, clearing and free
 * exploration arrive as actions, so the saved, unanchored and ad-hoc routes share one path.
 */
export function useGraphViewpointExploration(
  svc: ModelService,
  input: { adHoc: Ref<AdHocExecution | undefined>; rootId: Ref<string> },
  actions: ViewpointExplorationActions,
) {
  const { adHoc, rootId } = input
  const route = useRoute()
  const router = useRouter()

  const viewpoints = ref<ViewpointSummary[]>([])
  const viewpointDefinitions = ref<readonly ViewpointDefinitionEnvelope[]>([])
  const selectedViewpointSlug = ref<string | null>(null)
  const viewpointExecution = useViewpointExecution(svc)

  const loadViewpointCatalog = async () => {
    // Viewpoint discovery comes from the dedicated /api/viewpoints source, not authoring
    // guidance — the picker summaries are projected from the same definition envelopes.
    const definitions = await Effect.runPromise(svc.listViewpointDefinitions()).catch(() => [])
    viewpointDefinitions.value = definitions
    viewpoints.value = definitions.map(viewpointSummaryFromEnvelope)
  }

  const envelopeFor = (slug: string | null) =>
    viewpointDefinitions.value.find((d) => d.slug === slug)

  const selectedPresentation = computed<PresentationNode | null>(() => {
    if (adHoc.value) return adHoc.value.presentation
    const envelope = envelopeFor(selectedViewpointSlug.value)
    return envelope ? presentationFromMapping(envelope.presentation) : null
  })
  const currentRepresentation = computed(() => selectedPresentation.value?.representation ?? 'exploration')
  const entityStyleById = computed(() => projectionByItemId(viewpointExecution.projection.value))
  const connectionStyleIndex = computed(() =>
    buildConnectionStyleIndex(viewpointExecution.result.value?.connections ?? [], viewpointExecution.projection.value),
  )
  const connectionSummaryIndex = computed(() =>
    buildConnectionSummaryIndex(viewpointExecution.result.value?.connections ?? []),
  )
  const diagnostics = computed(() => computeExecutionDiagnostics(
    viewpointExecution.result.value, selectedPresentation.value, currentRepresentation.value,
  ))
  const selectedEnvelope = computed(() => envelopeFor(selectedViewpointSlug.value) ?? null)
  const legend = computed(() =>
    deriveLegend(selectedPresentation.value, viewpointExecution.projection.value?.rule_outcomes ?? []),
  )
  const scaleGradients = computed(() =>
    deriveScaleGradients(selectedPresentation.value, viewpointExecution.projection.value?.scale_legends ?? []),
  )

  const runViewpointExecution = async (resolved: ResolvedViewpointExecution) => {
    actions.clearGraph()
    // URL = state: the address always names the ON-SCREEN execution (slug + parameters).
    // Verification pins survive only a same-viewpoint re-run/reload — switching viewpoints
    // must never carry a previous reference's pins forward.
    const pins = route.query.viewpoint === resolved.slug
      ? Object.fromEntries(VERIFIED_KEYS.flatMap((key) =>
        typeof route.query[key] === 'string' ? [[key, route.query[key]]] : [],
      ))
      : {}
    void router.replace({ query: { ...executionQuery(resolved.slug, resolved.parameters), ...pins } })
    await viewpointExecution.execute(resolved)
    actions.populate()
  }
  const viewpointPrompt = useViewpointParameterPrompt(runViewpointExecution, viewpointDefinitions)
  const loadViewpointPopulation = (slug: string, preset?: ParameterDraft) => viewpointPrompt.run(slug, preset)

  // Ad-hoc exploration: execute an inline query + presentation directly (no slug/picker/URL),
  // then populate the graph from the same result the saved path uses.
  const runAdHocExploration = async () => {
    const execution = adHoc.value
    if (!execution) return
    actions.clearGraph()
    await viewpointExecution.execute(execution.request)
    actions.populate()
  }

  /** Where a definition asks to be read somewhere other than here — a table, a matrix, a diagram. */
  const redirectFor = (slug: string) => explorationRedirectFor(envelopeFor(slug))

  const onSelectViewpoint = (viewpoint: ViewpointSummary | null) => {
    selectedViewpointSlug.value = viewpoint?.slug ?? null
    if (!viewpoint) {
      viewpointExecution.clear()
      void router.replace({ query: rootId.value ? { id: rootId.value } : {} })
      actions.loadRoot()
      return
    }
    const redirect = redirectFor(viewpoint.slug)
    if (redirect) {
      void router.push(redirect)
      return
    }
    void loadViewpointPopulation(viewpoint.slug)
  }

  const rerunViewpoint = () => {
    if (selectedViewpointSlug.value) void loadViewpointPopulation(selectedViewpointSlug.value)
  }

  /** Reload or shared link: the address already names an execution, so run it without re-prompting. */
  const restoreFromAddress = () => {
    const viewpointSlug = route.query.viewpoint as string | undefined
    const preselected = viewpointSlug ? viewpoints.value.find((v) => v.slug === viewpointSlug) : undefined
    if (!preselected) return
    const redirect = redirectFor(preselected.slug)
    if (redirect) {
      void router.push(redirect)
      return
    }
    selectedViewpointSlug.value = preselected.slug
    void loadViewpointPopulation(preselected.slug, parametersFromQuery(route.query))
  }

  return {
    viewpoints, selectedViewpointSlug, viewpointExecution, viewpointPrompt,
    selectedPresentation, entityStyleById, connectionStyleIndex, connectionSummaryIndex,
    diagnostics, selectedEnvelope, legend, scaleGradients,
    loadViewpointCatalog, runAdHocExploration, restoreFromAddress, onSelectViewpoint, rerunViewpoint,
  }
}
