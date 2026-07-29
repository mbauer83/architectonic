<script setup lang="ts">
import { inject, ref, watch, computed } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import TypedPropertyInput from './TypedPropertyInput.vue'
import type { EntityAttributeDescriptor } from '../../domain'
import { hasVerificationErrors, readErrorMessage, collectVerificationIssues } from '../lib/errors'
import { WIZARD_DRAFT_KEYWORD } from './WizardDomainStage.helpers'
import { useSimilarEntities } from '../composables/useSimilarEntities'
import type { EntityDisplayInfo } from '../../domain'

// The form is the wizard's single create-or-reuse surface (no separate "find" mode): the name
// input doubles as the search box over existing same-type entities.
const componentProps = defineProps<{ entityType: string; namePlaceholder?: string }>()
const emit = defineEmits<{
  created: [{ artifactId: string; name: string }]
  cancel: []
  useExisting: [EntityDisplayInfo]
}>()

const svc = inject(modelServiceKey)!

const name = ref('')
const similar = useSimilarEntities(
  (query, entityType) =>
    Effect.runPromise(svc.searchEntityDisplay({ query, limit: 5, entityTypes: [entityType] }))
      .then((result) => result.items),
  () => componentProps.entityType,
  name,
)
const summary = ref('')
const propertyRows = ref<{ key: string; value: string }[]>([])
const showOptional = ref(false)
const schemaRequired = ref<Set<string>>(new Set())
const schemaOptional = ref<string[]>([])
const schemaDescriptors = ref<Record<string, EntityAttributeDescriptor>>({})

const busy = ref(false)
const formError = ref<string | null>(null)
const previewClean = ref(false)
const previewIssues = ref<string[]>([])

const requiredMissing = computed(() =>
  [...schemaRequired.value].some((key) => !(propertyRows.value.find((r) => r.key === key)?.value.trim())))

watch(() => componentProps.entityType, (type) => {
  schemaRequired.value = new Set()
  schemaOptional.value = []
  schemaDescriptors.value = {}
  propertyRows.value = []
  showOptional.value = false
  previewClean.value = false
  if (!type) return
  void Effect.runPromise(svc.getEntitySchemata(type)).then((info) => {
    schemaRequired.value = new Set(info.required)
    schemaOptional.value = info.properties.filter((p) => !info.required.includes(p))
    schemaDescriptors.value = info.descriptors
    propertyRows.value = info.required.map((key) => ({ key, value: info.descriptors[key]?.default ?? '' }))
  }).catch((error: unknown) => { formError.value = readErrorMessage(error) })
}, { immediate: true })

const revealOptional = () => {
  showOptional.value = true
  for (const key of schemaOptional.value) {
    if (!propertyRows.value.some((r) => r.key === key)) {
      propertyRows.value.push({ key, value: schemaDescriptors.value[key]?.default ?? '' })
    }
  }
}

const buildBody = (dryRun: boolean) => {
  const properties: Record<string, string> = {}
  for (const row of propertyRows.value) if (row.value.trim()) properties[row.key] = row.value
  return {
    artifact_type: componentProps.entityType,
    name: name.value.trim(),
    summary: summary.value.trim() || undefined,
    keywords: [WIZARD_DRAFT_KEYWORD],
    status: 'draft',
    version: '0.1.0',
    properties: Object.keys(properties).length ? properties : undefined,
    dry_run: dryRun,
  }
}

const doPreview = () => {
  if (!name.value.trim() || requiredMissing.value) return
  busy.value = true
  formError.value = null
  previewIssues.value = []
  void Effect.runPromise(svc.createEntity(buildBody(true)))
    .then((result) => {
      busy.value = false
      previewClean.value = !hasVerificationErrors(result.verification)
      if (!previewClean.value) previewIssues.value = collectVerificationIssues(result.verification)
    })
    .catch((error: unknown) => {
      busy.value = false
      formError.value = readErrorMessage(error)
    })
}

const doCreate = () => {
  busy.value = true
  formError.value = null
  void Effect.runPromise(svc.createEntity(buildBody(false)))
    .then((result) => {
      busy.value = false
      if (result.wrote) emit('created', { artifactId: result.artifact_id, name: name.value.trim() })
      else formError.value = result.content ?? 'Verification failed'
    })
    .catch((error: unknown) => {
      busy.value = false
      formError.value = readErrorMessage(error)
    })
}

watch(name, () => { previewClean.value = false })
</script>

<template>
  <div class="wizard-entity-form">
    <div class="form-row">
      <label class="form-label">Name <span class="required">*</span></label>
      <input
        v-model="name"
        class="form-input"
        :placeholder="namePlaceholder ?? 'A short, descriptive name'"
      >
      <span class="form-hint">Typing searches existing {{ entityType }}s — click a match to
        reuse it instead of creating a duplicate.</span>
    </div>

    <div
      v-if="similar.matches.value.length"
      class="similar-block"
    >
      <span class="similar-label">Existing — click to use instead:</span>
      <button
        v-for="match in similar.matches.value"
        :key="match.artifact_id"
        type="button"
        class="similar-chip"
        @click="emit('useExisting', match)"
      >
        {{ match.name }}
      </button>
    </div>

    <div class="form-row">
      <label class="form-label">Summary</label>
      <textarea
        v-model="summary"
        class="form-textarea"
        rows="2"
        placeholder="One or two sentences — what is this, and why does it belong here?"
      />
    </div>

    <div
      v-if="schemaRequired.size > 0"
      class="form-row"
    >
      <label class="form-label">Required properties</label>
      <div
        v-for="row in propertyRows.filter((r) => schemaRequired.has(r.key))"
        :key="row.key"
        class="prop-row"
      >
        <span class="prop-key">{{ row.key }}</span>
        <TypedPropertyInput
          v-model="row.value"
          :descriptor="schemaDescriptors[row.key] ?? { type: 'string' }"
          required
        />
      </div>
    </div>

    <button
      v-if="!showOptional && schemaOptional.length > 0"
      type="button"
      class="btn-link"
      @click="revealOptional"
    >
      + Show {{ schemaOptional.length }} more propert{{ schemaOptional.length === 1 ? 'y' : 'ies' }}
    </button>
    <div
      v-if="showOptional"
      class="form-row"
    >
      <div
        v-for="row in propertyRows.filter((r) => !schemaRequired.has(r.key))"
        :key="row.key"
        class="prop-row"
      >
        <span class="prop-key">{{ row.key }}</span>
        <TypedPropertyInput
          v-model="row.value"
          :descriptor="schemaDescriptors[row.key] ?? { type: 'string' }"
        />
      </div>
    </div>

    <div
      v-if="formError"
      class="state-msg state-msg--error"
    >
      {{ formError }}
    </div>
    <div
      v-if="previewIssues.length"
      class="state-msg state-msg--error"
    >
      <strong>Verification issues:</strong>
      <ul>
        <li
          v-for="issue in previewIssues"
          :key="issue"
        >
          {{ issue }}
        </li>
      </ul>
    </div>
    <div
      v-else-if="previewClean"
      class="state-msg state-msg--ok"
    >
      Looks good — ready to create.
    </div>

    <div class="form-actions">
      <button
        type="button"
        class="btn-cancel"
        @click="emit('cancel')"
      >
        Cancel
      </button>
      <button
        type="button"
        class="btn-preview"
        :disabled="busy || !name.trim() || requiredMissing"
        @click="doPreview"
      >
        Preview
      </button>
      <button
        type="button"
        class="btn-create"
        :disabled="busy || !previewClean"
        @click="doCreate"
      >
        Create
      </button>
    </div>
  </div>
</template>

<style scoped>
.wizard-entity-form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-label { font-size: 12px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: .04em; }
.required { color: #dc2626; }
.form-input, .form-textarea {
  padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px;
  outline: none; box-sizing: border-box; font-family: inherit;
}
.form-input:focus, .form-textarea:focus { border-color: #2563eb; }
.form-hint { font-size: 11px; color: #9ca3af; }
.similar-block { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.similar-label { font-size: 12px; color: #92400e; }
.similar-chip {
  padding: 2px 10px; border-radius: 12px; border: 1px solid #fcd34d; background: #fffbeb;
  color: #92400e; font-size: 12px; cursor: pointer;
}
.similar-chip:hover { background: #fef3c7; }
.prop-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.prop-key { flex: 0 0 160px; font-size: 12px; color: #4b5563; }
.btn-link { align-self: flex-start; background: none; border: none; color: #2563eb; cursor: pointer; padding: 0; font-size: 12px; text-decoration: underline; }
.state-msg { font-size: 12px; }
.state-msg--error { color: #dc2626; }
.state-msg--error ul { margin: 4px 0 0; padding-left: 18px; }
.state-msg--ok { color: #16a34a; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-cancel, .btn-preview, .btn-create {
  padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: none;
}
.btn-cancel { background: none; border: 1px solid #d1d5db; color: #6b7280; }
.btn-preview { background: #f3f4f6; border: 1px solid #bfdbfe; color: #1d4ed8; }
.btn-create { background: #16a34a; color: white; }
.btn-cancel:disabled, .btn-preview:disabled, .btn-create:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
