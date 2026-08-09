import { computed, ref, type Ref } from 'vue'
import { Exit } from 'effect'
import { useMutation } from './useMutation'
import { useQuery } from './useQuery'
import type { ModelService } from '../../application/ModelService'
import type { GroupList } from '../../domain/schemas/groups'
import type { Scratchpad, ScratchpadLift } from '../../domain/schemas/scratchpads'
import type { RepoError } from '../../ports/repositoryErrors'

/**
 * Preflighting a lift, then performing the same one.
 *
 * Held apart from the view for the reason the save policy is: this is a *sequence* — plan, look,
 * commit — and burying it in a click handler is how the second call ends up made against a
 * different selection than the first was planned for. The selection is captured when the dialog
 * opens and reused verbatim on execution, so what a person read is what runs.
 *
 * An empty selection means "everything on this scratchpad", resolved here rather than sent as one:
 * the server refuses an empty selection deliberately, because a mis-click must not lift a whole
 * canvas by accident.
 *
 * A target is chosen **per frame**, not per lift: the frames are work archetypes, so a canvas
 * routinely holds strategy work for one project and delivery work for another, and forcing one
 * destination would turn the ordinary act into four lifts with the selection rebuilt each time.
 */
export function useScratchpadLift(
  svc: ModelService,
  artifactId: Ref<string>,
  currentScratchpad: () => Scratchpad | null,
  onCommitted: (lifted: Scratchpad) => void,
) {
  const open = ref(false)
  const plan = ref<ScratchpadLift | null>(null)
  /** Frame id → project slug, for the frames this selection touches. Empty means the root model. */
  const targets = ref<Record<string, string>>({})
  /** The frames the selection actually spans, so the dialog asks once per frame rather than once
   * per frame the scratchpad happens to have. */
  const frames = ref<{ id: string; label: string }[]>([])
  const error = ref('')
  /** Frozen when the dialog opens: the plan on screen describes these notes and no others. */
  const selection = ref<string[]>([])

  const liftMutation = useMutation<ScratchpadLift, RepoError>()
  const groupsQuery = useQuery<GroupList, RepoError>()

  const projects = computed(() =>
    (groupsQuery.data.value?.['model-projects'] ?? [])
      .filter((group) => !group.archived)
      .map((group) => group.slug),
  )

  const run = async (dryRun: boolean): Promise<void> => {
    const current = currentScratchpad()
    if (!current) return
    error.value = ''
    const exit = await liftMutation.run(svc.liftScratchpad(artifactId.value, {
      version: current.version,
      selection: [...selection.value],
      targets: Object.fromEntries(
        Object.entries(targets.value).map(([frame, slug]) => [frame, slug.trim()]),
      ),
      'dry-run': dryRun,
    }))
    if (!Exit.isSuccess(exit)) {
      error.value = liftMutation.errorMessage.value ?? 'The lift could not be planned.'
      return
    }
    plan.value = exit.value
    if (exit.value.committed) onCommitted(current)
  }

  /** Open on a plan, never on an empty dialog: the preflight *is* the dialog's content. */
  const preflight = async (selected: readonly string[]): Promise<void> => {
    const current = currentScratchpad()
    selection.value = selected.length
      ? [...selected]
      : (current?.notes ?? []).map((note) => note.id)
    const spanned = new Set(
      (current?.notes ?? [])
        .filter((note) => selection.value.includes(note.id))
        .map((note) => note.area),
    )
    frames.value = [...spanned].sort().map((id) => ({
      id,
      label: (current?.areas ?? []).find((area) => area.id === id)?.label ?? id,
    }))
    plan.value = null
    open.value = true
    groupsQuery.run(svc.listGroups('model-project'))
    await run(true)
  }

  const close = (): void => {
    open.value = false
    plan.value = null
    error.value = ''
  }

  const setTarget = (frame: string, slug: string): void => {
    targets.value = { ...targets.value, [frame]: slug }
  }

  return {
    open,
    plan,
    targets,
    frames,
    setTarget,
    error,
    projects,
    selectionSize: computed(() => selection.value.length),
    busy: liftMutation.running,
    preflight,
    lift: () => run(false),
    close,
  }
}
