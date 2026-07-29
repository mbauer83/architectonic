import { computed, reactive, ref, watch, type InjectionKey, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { AuthoringGuidance, EntityAttributeDescriptor, EntityDetail } from '../../domain'
import { readErrorMessage } from '../lib/errors'
import { specializationOptionsForEntityType } from '../lib/specializationOptions'
import { NO_QUARANTINE, quarantineFromSchemaInfo } from '../lib/schemaQuarantine'
import { reconcileRowsWithSchema } from '../lib/schemaPropertyRows'

type AdHocType = 'string' | 'integer' | 'number' | 'boolean' | 'array'
const ADHOC_VALID = new Set<string>(['string', 'integer', 'number', 'boolean', 'array'])

const toLexical = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'string') return v
  // Arrays and other objects arrive as JSON from the backend
  return JSON.stringify(v)
}

/**
 * Owns the entity-detail view's whole edit-form lifecycle: entering/leaving edit mode,
 * every editable field, ad-hoc vs. schema-typed property rows, dry-run preview, and save —
 * plus the summary/notes reference-picker insertion (their textareas belong to this same
 * transaction). Returned as one `reactive()` bundle rather than individual refs so both the
 * header (name/status fields, action buttons) and the edit-form card (everything else) can
 * read/call it directly off one prop, with plain-object property access (no `.value`
 * threading, no per-field v-model plumbing across components).
 */
export function useEntityEditForm(options: {
  svc: ModelService
  entityId: Ref<string>
  detail: Ref<EntityDetail | null>
  editFn: Ref<ModelService['editEntity'] | ModelService['adminEditEntity']>
  onSaved: (newArtifactId: string) => void
}) {
  const { svc, entityId, detail, editFn, onSaved } = options

  const editing = ref(false)
  const editName = ref('')
  const editSummary = ref('')
  const editKeywords = ref('')
  const editStatus = ref('')
  const editProperties = ref<{ key: string; value: string; adHocType: AdHocType }[]>([])
  const editNotes = ref('')
  // A concept may carry several specializations (§15.2); the schema merges all of them.
  const editSpecializations = ref<string[]>([])
  const editTypeGuidance = ref<AuthoringGuidance | null>(null)
  const editBusy = ref(false)
  const editError = ref<string | null>(null)
  const editPreview = ref<{ content: string | null; warnings: string[] } | null>(null)
  const showReferencePicker = ref(false)
  const activeReferenceField = ref<'summary' | 'notes'>('summary')
  const summaryTextareaRef = ref<HTMLTextAreaElement | null>(null)
  const notesTextareaRef = ref<HTMLTextAreaElement | null>(null)
  const editSchemaDescriptors = ref<Record<string, EntityAttributeDescriptor>>({})
  const editSchemaRequired = ref<Set<string>>(new Set())
  // Class-B quarantine for the edited (type, specialization) pair. The write boundary
  // refuses the save regardless; this only lets the form say so first (WU-S2).
  const editQuarantine = ref(NO_QUARANTINE)

  const editArtifactType = computed(() => detail.value?.artifact_type ?? '')
  const editSpecializationOptions = computed(() =>
    detail.value ? specializationOptionsForEntityType(editTypeGuidance.value, detail.value.artifact_type) : [],
  )
  const editRequiredMissing = computed(() =>
    [...editSchemaRequired.value].some((key) => {
      const row = editProperties.value.find((r) => r.key === key)
      return !row || !row.value.trim()
    }),
  )

  // Guards against out-of-order schema responses when the specialization changes quickly.
  let schemaRequestSeq = 0
  // The schema keys from the previous load, so a specialization change reconciles rather than
  // appends: a value survives where the new profile still declares its attribute, and a row
  // that existed only because the old profile listed it (and is still empty) is dropped.
  let previousSchemaKeys: string[] = []

  const loadEffectiveSchema = (artifactType: string, specialization: string): void => {
    const requestId = ++schemaRequestSeq
    void Effect.runPromise(svc.getEntitySchemata(artifactType, specialization))
      .then((info) => {
        if (requestId !== schemaRequestSeq) return
        editSchemaDescriptors.value = info.descriptors
        editSchemaRequired.value = new Set(info.required)
        editQuarantine.value = quarantineFromSchemaInfo(info)
        editProperties.value = reconcileRowsWithSchema(editProperties.value, previousSchemaKeys, info)
        previousSchemaKeys = [...info.properties]
      })
      .catch(() => {
        if (requestId !== schemaRequestSeq) return
        editSchemaDescriptors.value = {}
        editSchemaRequired.value = new Set()
        editQuarantine.value = NO_QUARANTINE
        previousSchemaKeys = []
      })
  }

  // startEdit seeds editSpecialization programmatically and loads the schema itself;
  // that seed must not re-trigger the watcher's reload.
  let specializationSeededByStartEdit = false

  watch(editSpecializations, () => {
    if (specializationSeededByStartEdit) {
      specializationSeededByStartEdit = false
      return
    }
    if (!editing.value) return
    const d = detail.value
    if (!d) return
    loadEffectiveSchema(d.artifact_type, editSpecializations.value.join(','))
  }, { deep: true })

  const startEdit = (): void => {
    const d = detail.value
    if (!d) return
    // Fresh transaction: the reconcile must treat the entity's current properties as real
    // data, not rows left over from a prior edit's schema.
    previousSchemaKeys = []
    editName.value = d.name
    editSummary.value = d.summary ?? ''
    editKeywords.value = (d.keywords ?? []).join(', ')
    editStatus.value = d.status
    editNotes.value = d.notes ?? ''
    const current = d.specializations ?? (d.specialization ? [d.specialization] : [])
    if (editSpecializations.value.join(',') !== current.join(',')) {
      specializationSeededByStartEdit = true
      editSpecializations.value = [...current]
    }
    editTypeGuidance.value = null
    void Effect.runPromise(svc.getAuthoringGuidance({ entityTypes: [d.artifact_type] }))
      .then((info) => { editTypeGuidance.value = info })
      .catch(() => { editTypeGuidance.value = null })
    const rawAttrTypes = d.extra?.['attribute-types']
    const savedAttrTypes: Record<string, AdHocType> =
      rawAttrTypes && typeof rawAttrTypes === 'object' && !Array.isArray(rawAttrTypes)
        ? Object.fromEntries(
            Object.entries(rawAttrTypes as Record<string, unknown>)
              .filter(([, v]) => ADHOC_VALID.has(String(v)))
              .map(([k, v]) => [k, String(v) as AdHocType]),
          )
        : {}
    editProperties.value = Object.entries(d.properties ?? {}).map(([key, value]) => ({
      key,
      value: toLexical(value),
      adHocType: savedAttrTypes[key] ?? 'string',
    }))
    editPreview.value = null
    editError.value = null
    editing.value = true
    loadEffectiveSchema(d.artifact_type, editSpecializations.value.join(','))
  }

  const cancelEdit = (): void => {
    editing.value = false
    editPreview.value = null
    editError.value = null
  }

  const addPropertyRow = (): void => {
    editProperties.value.push({ key: '', value: '', adHocType: 'string' })
  }

  const removePropertyRow = (i: number): void => {
    editProperties.value.splice(i, 1)
  }

  const buildEditBody = (dryRun: boolean): Record<string, unknown> => {
    const props: Record<string, string> = {}
    const adhocTypes: Record<string, string> = {}
    for (const row of editProperties.value) {
      const k = row.key.trim()
      if (!k) continue
      props[k] = row.value
      if (!editSchemaDescriptors.value[k] && row.adHocType !== 'string') {
        adhocTypes[k] = row.adHocType
      }
    }
    const kws = editKeywords.value.split(',').map((k: string) => k.trim()).filter(Boolean)
    return {
      artifact_id: entityId.value,
      name: editName.value || undefined,
      summary: editSummary.value || undefined,
      keywords: kws.length ? kws : undefined,
      status: editStatus.value || undefined,
      properties: props,
      attribute_types: Object.keys(adhocTypes).length ? adhocTypes : undefined,
      notes: editNotes.value || undefined,
      specializations: editSpecializations.value.length ? editSpecializations.value : undefined,
      dry_run: dryRun,
    }
  }

  const previewEdit = (): void => {
    editBusy.value = true
    editError.value = null
    editPreview.value = null
    void Effect.runPromise(editFn.value(buildEditBody(true) as Parameters<ModelService['editEntity']>[0])).then((r) => {
      editBusy.value = false
      editPreview.value = { content: r.content, warnings: [...r.warnings] }
    }).catch((reason: unknown) => {
      editBusy.value = false
      editError.value = readErrorMessage(reason)
    })
  }

  const saveEdit = (): void => {
    editBusy.value = true
    editError.value = null
    void Effect.runPromise(editFn.value(buildEditBody(false) as Parameters<ModelService['editEntity']>[0])).then((r) => {
      editBusy.value = false
      if (r.wrote) {
        editing.value = false
        editPreview.value = null
        onSaved(r.artifact_id)
      } else {
        editError.value = r.content ?? 'Verification failed'
      }
    }).catch((reason: unknown) => {
      editBusy.value = false
      editError.value = readErrorMessage(reason)
    })
  }

  const openReferencePicker = (field: 'summary' | 'notes'): void => {
    activeReferenceField.value = field
    showReferencePicker.value = true
  }

  const insertReference = (markdownLink: string): void => {
    const textarea = activeReferenceField.value === 'summary' ? summaryTextareaRef.value : notesTextareaRef.value
    if (!textarea) return
    const start = textarea.selectionStart ?? textarea.value.length
    const end = textarea.selectionEnd ?? start
    const currentValue = activeReferenceField.value === 'summary' ? editSummary.value : editNotes.value
    const nextValue = `${currentValue.slice(0, start)}${markdownLink}${currentValue.slice(end)}`
    if (activeReferenceField.value === 'summary') editSummary.value = nextValue
    else editNotes.value = nextValue
    requestAnimationFrame(() => {
      textarea.focus()
      const cursor = start + markdownLink.length
      textarea.setSelectionRange(cursor, cursor)
    })
  }

  return reactive({
    editing,
    editName,
    editSummary,
    editKeywords,
    editStatus,
    editProperties,
    editNotes,
    editSpecializations,
    editTypeGuidance,
    editArtifactType,
    editSpecializationOptions,
    editBusy,
    editError,
    editPreview,
    showReferencePicker,
    activeReferenceField,
    summaryTextareaRef,
    notesTextareaRef,
    editSchemaDescriptors,
    editSchemaRequired,
    editQuarantine,
    editRequiredMissing,
    startEdit,
    cancelEdit,
    addPropertyRow,
    removePropertyRow,
    previewEdit,
    saveEdit,
    openReferencePicker,
    insertReference,
  })
}

export type EntityEditFormApi = ReturnType<typeof useEntityEditForm>

/** Provided by EntityDetailView, injected by EntityDetailHeader/EntityEditFormCard —
 * provide/inject rather than a prop so the shared bundle's field mutations (`edit.editName =
 * ...` via v-model) aren't flagged by `vue/no-mutating-props`: it was never a prop to begin
 * with, by design, since every consumer legitimately co-owns this one edit transaction. */
export const entityEditFormKey: InjectionKey<EntityEditFormApi> = Symbol('entityEditForm')
