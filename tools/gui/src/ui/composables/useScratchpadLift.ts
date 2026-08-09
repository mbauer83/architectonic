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
 */
export function useScratchpadLift(
  svc: ModelService,
  artifactId: Ref<string>,
  currentScratchpad: () => Scratchpad | null,
  onCommitted: (lifted: Scratchpad) => void,
) {
  const open = ref(false)
  const plan = ref<ScratchpadLift | null>(null)
  const target = ref('')
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
      target: target.value.trim(),
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

  return {
    open,
    plan,
    target,
    error,
    projects,
    selectionSize: computed(() => selection.value.length),
    busy: liftMutation.running,
    preflight,
    lift: () => run(false),
    close,
  }
}
