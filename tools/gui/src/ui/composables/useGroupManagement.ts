import { ref, computed, inject } from 'vue'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import { modelServiceKey } from '../keys'

export interface GroupOption {
  slug: string
  name: string
  count?: number
  archived?: boolean
  meta_ontology?: string
  type_filter?: string[]
}

export const useGroupManagement = (opts: { axis: string; onMutated: () => void }) => {
  const svc = inject(modelServiceKey)!

  const dialog = ref<'create' | 'rename' | 'archive' | 'delete' | null>(null)
  const dialogTarget = ref<GroupOption | null>(null)
  const fieldName = ref('')
  const fieldSlug = ref('')
  const fieldConfirm = ref('')
  const dialogError = ref('')
  const busy = ref(false)

  const slugify = (s: string) =>
    s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

  const extractError = (e: unknown): string => {
    const raw = e instanceof NetworkError ? e.message : String(e)
    try {
      const parsed: unknown = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && 'detail' in parsed)
        return String((parsed as Record<string, unknown>).detail)
      return raw
    } catch { return raw }
  }

  const closeDialog = () => {
    dialog.value = null; dialogTarget.value = null; dialogError.value = ''
  }
  const openCreate = () => {
    dialog.value = 'create'; fieldName.value = ''; fieldSlug.value = ''; dialogError.value = ''
  }
  const openRename = (g: GroupOption) => {
    dialogTarget.value = g; dialog.value = 'rename'; fieldName.value = g.name; dialogError.value = ''
  }
  const openArchive = (g: GroupOption) => {
    dialogTarget.value = g; dialog.value = 'archive'; fieldConfirm.value = ''; dialogError.value = ''
  }
  const openDelete = (g: GroupOption) => {
    dialogTarget.value = g; dialog.value = 'delete'; fieldConfirm.value = ''; dialogError.value = ''
  }

  const run = async (effect: Effect.Effect<unknown, unknown>) => {
    busy.value = true; dialogError.value = ''
    try {
      await Effect.runPromise(effect)
      closeDialog()
      opts.onMutated()
    } catch (e) { dialogError.value = extractError(e) }
    finally { busy.value = false }
  }

  const archiveNeedsConfirm = computed(() =>
    !dialogTarget.value?.archived && (dialogTarget.value?.count ?? 0) > 0)
  const archiveReady = computed(() =>
    !archiveNeedsConfirm.value || fieldConfirm.value === dialogTarget.value?.slug)
  const deleteNeedsConfirm = computed(() => (dialogTarget.value?.count ?? 0) > 0)
  const deleteReady = computed(() =>
    !deleteNeedsConfirm.value || fieldConfirm.value === dialogTarget.value?.slug)

  const submitCreate = () => {
    if (!fieldSlug.value || !fieldName.value) return
    void run(svc.createGroup({ kind: opts.axis, slug: fieldSlug.value, name: fieldName.value }))
  }
  const submitRename = () => {
    if (!dialogTarget.value) return
    void run(svc.renameGroup({ kind: opts.axis, target: dialogTarget.value.slug, name: fieldName.value }))
  }
  const submitArchive = () => {
    if (!dialogTarget.value) return
    const g = dialogTarget.value
    const confirmArg = !g.archived && (g.count ?? 0) > 0 ? fieldConfirm.value : undefined
    void run(g.archived
      ? svc.unarchiveGroup({ kind: opts.axis, target: g.slug })
      : svc.archiveGroup({ kind: opts.axis, target: g.slug, confirm: confirmArg }))
  }
  const submitDelete = () => {
    if (!dialogTarget.value) return
    void run(svc.deleteGroup({
      kind: opts.axis,
      target: dialogTarget.value.slug,
      confirm: fieldConfirm.value || undefined,
    }))
  }

  return {
    dialog, dialogTarget, fieldName, fieldSlug, fieldConfirm, dialogError, busy,
    slugify, closeDialog, openCreate, openRename, openArchive, openDelete,
    archiveNeedsConfirm, archiveReady, deleteNeedsConfirm, deleteReady,
    submitCreate, submitRename, submitArchive, submitDelete,
  }
}
