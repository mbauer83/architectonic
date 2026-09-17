import { computed, ref, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramViewpointProjection, ViewpointSummary } from '../../domain'
import { findViewpointBySlug } from '../components/ViewpointSelect.helpers'
import { loadViewpointSummaries } from '../lib/viewpointSummary'
import { isStalePin } from '../views/EditDiagramView.helpers'

/**
 * The viewpoint an edit is made under: which one, which version it is pinned to, and what the
 * saved diagram's projection says about that pin.
 *
 * Owned apart from the view so the view stays the composition of its parts. `refreshDiscovery` is
 * late-bound: choosing or dismissing a viewpoint changes what the entity search should offer, and
 * the selection that owns discovery is created after this and needs the slug from here.
 */
export function useDiagramEditViewpoint(options: {
  svc: ModelService
  diagramId: Ref<string>
  refreshDiscovery: () => void
}) {
  const { svc, diagramId, refreshDiscovery } = options

  const viewpoints = ref<ViewpointSummary[]>([])
  const viewpointSlug = ref<string | null>(null)
  const viewpointPinnedVersion = ref<number | null>(null)
  const viewpointProjection = ref<DiagramViewpointProjection | null>(null)
  const hideInsteadOfGhost = ref(false)

  const loadViewpoints = async (): Promise<void> => {
    viewpoints.value = await loadViewpointSummaries(svc.listViewpointDefinitions())
  }

  const loadProjection = async (): Promise<void> => {
    if (!diagramId.value) return
    viewpointProjection.value = await Effect.runPromise(svc.getViewpointProjection(diagramId.value)).catch(() => null)
  }

  const onSelectViewpoint = (viewpoint: ViewpointSummary | null): void => {
    viewpointPinnedVersion.value = viewpoint?.version ?? null
    refreshDiscovery()
  }

  const currentDefinitionVersion = computed(
    () => findViewpointBySlug(viewpoints.value, viewpointSlug.value)?.version ?? null,
  )
  const stalePin = computed(() => isStalePin(viewpointProjection.value))

  const doRePin = (): void => {
    if (currentDefinitionVersion.value !== null) viewpointPinnedVersion.value = currentDefinitionVersion.value
  }

  const dismissViewpoint = (): void => {
    viewpointSlug.value = null
    viewpointPinnedVersion.value = null
    refreshDiscovery()
  }

  /** What a save records: the chosen slug at its pinned version, else the current definition's. */
  const forWrite = () => viewpointSlug.value
    ? { slug: viewpointSlug.value, version: viewpointPinnedVersion.value ?? currentDefinitionVersion.value ?? 1 }
    : null

  return {
    viewpoints, viewpointSlug, viewpointPinnedVersion, viewpointProjection, hideInsteadOfGhost,
    loadViewpoints, loadProjection, onSelectViewpoint, currentDefinitionVersion, stalePin, doRePin,
    dismissViewpoint, forWrite,
  }
}
