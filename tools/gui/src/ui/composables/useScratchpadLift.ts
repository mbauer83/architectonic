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
 *
 * `settle` is what makes the plan describe the canvas on screen. A lift is planned by the *server*,
 * against the *stored* scratchpad, while the canvas writes on an idle timer — so a person who
 * writes two notes and lifts them straight away asks about notes that only exist in their browser,
 * and is told "the selection names notes this scratchpad does not have". That refusal is about
 * nothing, and the browser suite found it. Every request here waits for the canvas to be at rest
 * first, which is a property of the sequence rather than of either call.
 */
export function useScratchpadLift(
  svc: ModelService,
  artifactId: Ref<string>,
  currentScratchpad: () => Scratchpad | null,
  onCommitted: (lifted: Scratchpad) => void,
  settle: () => Promise<void>,
) {
  const open = ref(false)
  const plan = ref<ScratchpadLift | null>(null)
  /** Frame id → project slug, for the frames this selection touches. Empty means the root model. */
  const targets = ref<Record<string, string>>({})
  /** The frames the selection actually spans, so the dialog asks once per frame rather than once
   * per frame the scratchpad happens to have. */
  const frames = ref<{ id: string; label: string }[]>([])
  /** Whether to draw a view of what was lifted. Off by default: the diagram is second-order, and a
   * picture nobody asked for is a file nobody expected. */
  const draw = ref(false)
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
    // The canvas first, then the question. Read after the flush, never before: a save answers with
    // the new version, and asking with the old one is refused as stale.
    await settle()
    const current = currentScratchpad()
    if (!current) return
    error.value = ''
    const exit = await liftMutation.run(svc.liftScratchpad(artifactId.value, {
      version: current.version,
      selection: [...selection.value],
      targets: Object.fromEntries(
        Object.entries(targets.value).map(([frame, slug]) => [frame, slug.trim()]),
      ),
      draw: draw.value,
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
    draw,
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
