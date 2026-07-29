<script setup lang="ts">
import { inject, onMounted, ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import TypedPropertyInput from '../components/TypedPropertyInput.vue'
import type { WriteHelp, WriteResult, EntityAttributeDescriptor, AuthoringGuidance } from '../../domain'
import { hasVerificationErrors, readErrorMessage, collectVerificationIssues } from '../lib/errors'
import { specializationOptionsForEntityType, specializationOptionLabel } from '../lib/specializationOptions'
import { reconcileRowsWithSchema, rowsFromSchema } from '../lib/schemaPropertyRows'
import SchemaQuarantineBanner from '../components/SchemaQuarantineBanner.vue'
import { NO_QUARANTINE, quarantineFromSchemaInfo } from '../lib/schemaQuarantine'
import { createBlockedReason, previewBlockedReason } from './EntityCreateView.helpers'

const svc = inject(modelServiceKey)!
const router = useRouter()

const writeHelp = ref<WriteHelp | null>(null)

onMounted(() => {
  void Effect.runPromise(svc.getWriteHelp())
    .then((help) => {
      writeHelp.value = help
    })
    .catch((error: unknown) => {
      formError.value = readErrorMessage(error)
    })
})

// ── Form state ────────────────────────────────────────────────────────────────

type AdHocType = 'string' | 'integer' | 'number' | 'boolean' | 'array'

const artifactType = ref('')
const name = ref('')
const summary = ref('')
const keywords = ref('')
const status = ref('draft')
const version = ref('0.1.0')
const properties = ref<{ key: string; value: string; adHocType: AdHocType }[]>([])
const notes = ref('')
// A concept may carry several specializations (§15.2); the schema merges all of them.
const specializations = ref<string[]>([])
const typeGuidance = ref<AuthoringGuidance | null>(null)
const specializationOptions = computed(() =>
  specializationOptionsForEntityType(typeGuidance.value, artifactType.value),
)

const busy = ref(false)
const formError = ref<string | null>(null)
const preview = ref<WriteResult | null>(null)
const previewClean = ref(false)
const previewIssues = ref<string[]>([])

// ── Schema-driven properties ──────────────────────────────────────────────────

const schemaProps = ref<string[]>([])
const schemaRequired = ref<Set<string>>(new Set())
const schemaDescriptors = ref<Record<string, EntityAttributeDescriptor>>({})
const quarantine = ref(NO_QUARANTINE)

const createRequiredMissing = computed(() =>
  [...schemaRequired.value].some((key) => {
    const row = properties.value.find((r) => r.key === key)
    return !row || !row.value.trim()
  }),
)

// Guards against out-of-order schema responses when type/specialization change quickly.
let schemaRequestSeq = 0

const loadEffectiveSchema = (type: string, spec: string, preserveRows: boolean) => {
  const requestId = ++schemaRequestSeq
  void Effect.runPromise(svc.getEntitySchemata(type, spec))
    .then((info) => {
      if (requestId !== schemaRequestSeq) return
      const previousSchemaKeys = schemaProps.value
      schemaProps.value = [...info.properties]
      schemaRequired.value = new Set(info.required)
      schemaDescriptors.value = info.descriptors
      quarantine.value = quarantineFromSchemaInfo(info)
      properties.value = preserveRows
        ? reconcileRowsWithSchema(properties.value, previousSchemaKeys, info)
        : rowsFromSchema(info)
    })
    .catch((error: unknown) => {
      if (requestId !== schemaRequestSeq) return
      schemaProps.value = []
      schemaRequired.value = new Set()
      schemaDescriptors.value = {}
      quarantine.value = NO_QUARANTINE
      formError.value = readErrorMessage(error)
    })
}

// A type switch resets the specialization; that programmatic reset must not
// re-run the specialization watcher's row-preserving reload across types.
let specializationResetByTypeChange = false

watch(artifactType, (newType) => {
  if (specializations.value.length) {
    specializationResetByTypeChange = true
    specializations.value = []
  }
  typeGuidance.value = null
  if (!newType) {
    schemaRequestSeq += 1
    schemaProps.value = []
    schemaRequired.value = new Set()
    schemaDescriptors.value = {}
    quarantine.value = NO_QUARANTINE
    return
  }
  loadEffectiveSchema(newType, '', false)
  void Effect.runPromise(svc.getAuthoringGuidance({ entityTypes: [newType] }))
    .then((info) => {
      typeGuidance.value = info
    })
    .catch(() => {
      typeGuidance.value = null
    })
})

watch(specializations, () => {
  if (specializationResetByTypeChange) {
    specializationResetByTypeChange = false
    return
  }
  if (!artifactType.value) return
  // The effective schema changes with the specialization set; re-preview before create.
  preview.value = null
  previewClean.value = false
  loadEffectiveSchema(artifactType.value, specializations.value.join(','), true)
}, { deep: true })

watch(name, () => {
  // Reset preview state when name changes - forces user to re-preview
  preview.value = null
  previewClean.value = false
})

// ── Property rows ─────────────────────────────────────────────────────────────

const addPropRow = () => properties.value.push({ key: '', value: '', adHocType: 'string' })
const removePropRow = (i: number) => properties.value.splice(i, 1)

// ── Build body ────────────────────────────────────────────────────────────────

const buildBody = (dryRun: boolean) => {
  const props: Record<string, string> = {}
  const adhocTypes: Record<string, string> = {}
  for (const row of properties.value) {
    const k = row.key.trim()
    if (!k) continue
    props[k] = row.value
    if (!schemaDescriptors.value[k] && row.adHocType !== 'string') {
      adhocTypes[k] = row.adHocType
    }
  }
  const kws = keywords.value.split(',').map(k => k.trim()).filter(Boolean)
  return {
    artifact_type: artifactType.value,
    name: name.value,
    summary: summary.value || undefined,
    keywords: kws.length ? kws : undefined,
    status: status.value,
    version: version.value,
    properties: Object.keys(props).length ? props : undefined,
    attribute_types: Object.keys(adhocTypes).length ? adhocTypes : undefined,
    notes: notes.value || undefined,
    specializations: specializations.value.length ? specializations.value : undefined,
    dry_run: dryRun,
  }
}

// ── Preview ───────────────────────────────────────────────────────────────────

const doPreview = () => {
  if (!artifactType.value || !name.value.trim()) {
    formError.value = 'Artifact type and name are required.'
    return
  }
  busy.value = true
  formError.value = null
  preview.value = null
  previewClean.value = false
  previewIssues.value = []
  void Effect.runPromise(svc.createEntity(buildBody(true)))
    .then((result) => {
      busy.value = false
      preview.value = result
      previewClean.value = !hasVerificationErrors(result.verification)
      if (!previewClean.value) {
        previewIssues.value = collectVerificationIssues(result.verification)
      }
    })
    .catch((error: unknown) => {
      busy.value = false
      formError.value = readErrorMessage(error)
    })
}

// ── Create ────────────────────────────────────────────────────────────────────

const doCreate = () => {
  busy.value = true
  formError.value = null
  void Effect.runPromise(svc.createEntity(buildBody(false)))
    .then((result) => {
      busy.value = false
      if (result.wrote) {
        void router.push({ path: '/entity', query: { id: result.artifact_id } })
      } else {
        formError.value = result.content ?? 'Verification failed'
      }
    })
    .catch((error: unknown) => {
      busy.value = false
      formError.value = readErrorMessage(error)
    })
}
</script>

<template>
  <div class="create-layout">
    <div class="page-header">
      <button
        class="back-link"
        @click="router.back()"
      >
        ← Back
      </button>
      <h1 class="page-title">
        Create Entity
      </h1>
    </div>

    <div class="form-and-preview">
      <!-- Form -->
      <section class="form-section card">
        <div class="form-row">
          <label class="form-label">Artifact Type <span class="required">*</span></label>
          <select
            v-model="artifactType"
            class="form-select"
          >
            <option
              value=""
              disabled
            >
              Select type...
            </option>
            <template v-if="writeHelp">
              <optgroup
                v-for="(types, domain) in writeHelp.entity_types_by_domain"
                :key="domain"
                :label="domain"
              >
                <option
                  v-for="t in types"
                  :key="t"
                  :value="t"
                >
                  {{ t }}
                </option>
              </optgroup>
            </template>
          </select>
        </div>

        <div
          v-if="specializationOptions.length"
          class="form-row"
        >
          <label class="form-label">
            Specializations <span class="form-hint">(optional; ⌘/Ctrl-click for several)</span>
          </label>
          <select
            v-model="specializations"
            class="form-select"
            multiple
            size="4"
          >
            <option
              v-for="spec in specializationOptions"
              :key="spec.slug"
              :value="spec.slug"
            >
              {{ specializationOptionLabel(spec) }}
            </option>
          </select>
        </div>

        <SchemaQuarantineBanner
          :quarantine="quarantine"
          :artifact-type="artifactType"
          :specialization="specializations.join(', ')"
        />

        <div class="form-row">
          <label class="form-label">Name <span class="required">*</span></label>
          <input
            v-model="name"
            class="form-input"
            placeholder="Human-readable name"
          >
        </div>

        <div class="form-row">
          <label class="form-label">Summary</label>
          <textarea
            v-model="summary"
            class="form-textarea"
            rows="3"
            placeholder="Short description..."
          />
        </div>

        <div class="form-row">
          <label class="form-label">Keywords <span class="form-hint">(comma-separated)</span></label>
          <input
            v-model="keywords"
            class="form-input"
            placeholder="e.g. model, tooling, automation"
          >
        </div>

        <div class="form-row two-col">
          <div>
            <label class="form-label">Status</label>
            <select
              v-model="status"
              class="form-select"
            >
              <option value="draft">
                draft
              </option>
              <option value="active">
                active
              </option>
              <option value="deprecated">
                deprecated
              </option>
            </select>
          </div>
          <div>
            <label class="form-label">Version</label>
            <input
              v-model="version"
              class="form-input"
              placeholder="0.1.0"
            >
          </div>
        </div>

        <div class="form-row">
          <label class="form-label">Properties</label>
          <div
            v-for="(row, i) in properties"
            :key="i"
            class="prop-row"
          >
            <span
              v-if="schemaProps.includes(row.key)"
              class="prop-key-label"
              :title="row.key"
            >{{ row.key }}<span
              v-if="schemaRequired.has(row.key)"
              class="required"
            > *</span></span>
            <input
              v-else
              :value="row.key"
              class="prop-key"
              placeholder="key"
              @input="row.key = ($event.target as HTMLInputElement).value"
            >
            <TypedPropertyInput
              v-if="schemaDescriptors[row.key]"
              v-model="row.value"
              :descriptor="schemaDescriptors[row.key]"
              :required="schemaRequired.has(row.key)"
            />
            <template v-else>
              <select
                v-model="row.adHocType"
                class="prop-type-select"
                title="Value type"
                @change="row.value = row.adHocType === 'boolean' ? 'false' : ''"
              >
                <option value="string">
                  text
                </option>
                <option value="integer">
                  integer
                </option>
                <option value="number">
                  number
                </option>
                <option value="boolean">
                  boolean
                </option>
                <option value="array">
                  array
                </option>
              </select>
              <TypedPropertyInput
                v-model="row.value"
                :descriptor="{ type: row.adHocType }"
              />
            </template>
            <button
              class="remove-prop-btn icon-btn"
              :disabled="schemaRequired.has(row.key)"
              @click="removePropRow(i)"
            >
              ×
            </button>
          </div>
          <button
            class="add-prop-btn"
            @click="addPropRow"
          >
            + Add property
          </button>
        </div>

        <div class="form-row">
          <label class="form-label">Notes</label>
          <textarea
            v-model="notes"
            class="form-textarea"
            rows="3"
            placeholder="Additional notes..."
          />
        </div>

        <div
          v-if="formError"
          class="state-msg state-msg--error"
        >
          {{ formError }}
        </div>

        <div class="form-actions">
          <button
            class="preview-btn"
            :disabled="busy || createRequiredMissing || quarantine.quarantined"
            :title="previewBlockedReason(quarantine.quarantined, createRequiredMissing)"
            @click="doPreview"
          >
            Preview
          </button>
          <button
            class="create-btn"
            :disabled="busy || !previewClean || createRequiredMissing || quarantine.quarantined"
            :title="createBlockedReason(quarantine.quarantined, previewClean, createRequiredMissing)"
            @click="doCreate"
          >
            Create
          </button>
        </div>
      </section>

      <!-- Preview pane -->
      <section
        v-if="preview"
        class="preview-section card"
      >
        <h2 class="preview-title">
          Dry-run preview
        </h2>
        <div class="preview-meta">
          <span class="mono">{{ preview.artifact_id }}</span>
          <span class="preview-path mono">→ {{ preview.path }}</span>
        </div>

        <div
          v-if="!previewClean"
          class="state-msg state-msg--error"
        >
          <strong>Verification issues found:</strong>
          <ul style="margin-top: 4px; font-size: 12px; margin-bottom: 0; padding-left: 18px;">
            <li
              v-for="issue in previewIssues"
              :key="issue"
            >
              {{ issue }}
            </li>
          </ul>
        </div>
        <div
          v-else
          class="state-msg state-msg--ok"
        >
          Verification passed.
        </div>

        <pre
          v-if="preview.content"
          class="preview-content"
        >{{ preview.content }}</pre>
      </section>
    </div>
  </div>
</template>

<style scoped>
.create-layout { max-width: 1160px; margin: 0 auto; }

.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.back-link { font-size: 13px; color: #6b7280; background: none; border: none; cursor: pointer; padding: 0; }
.back-link:hover { color: #374151; }
.page-title { font-size: 20px; font-weight: 600; }

.form-and-preview { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
@media (max-width: 800px) { .form-and-preview { grid-template-columns: 1fr; } }

.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 20px; }

.form-row { margin-bottom: 14px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-label {
  display: block; font-size: 12px; font-weight: 600; color: #374151;
  margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em;
}
.required { color: #dc2626; }
.form-hint { font-weight: 400; text-transform: none; color: #9ca3af; }
.form-input, .form-textarea, .form-select {
  width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 13px; outline: none; box-sizing: border-box;
}
.form-textarea { resize: vertical; font-family: inherit; }
.form-select { background: white; }
.form-input:focus, .form-textarea:focus, .form-select:focus { border-color: #2563eb; }

.prop-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start; }
.prop-key-label {
  flex: 0 0 150px; font-size: 12px; font-weight: 500; color: #374151;
  padding-top: 7px; overflow-wrap: break-word; min-width: 0; }
.prop-key {
  flex: 0 0 150px; padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 12px; outline: none; box-sizing: border-box; min-width: 0;
}
.prop-key:focus { border-color: #2563eb; }
.prop-type-select {
  flex: 0 0 auto; padding: 6px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 12px; color: #374151; background: white; outline: none; cursor: pointer;
}
.prop-type-select:focus { border-color: #2563eb; }
.prop-row .icon-btn { margin-top: 5px; }
.icon-btn {
  width: 22px; height: 22px; border-radius: 4px; border: 1px solid #d1d5db;
  background: white; cursor: pointer; font-size: 14px; line-height: 1;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.remove-prop-btn { border-color: #fecaca; color: #dc2626; }
.remove-prop-btn:hover { background: #fef2f2; }
.add-prop-btn {
  font-size: 12px; color: #2563eb; background: none; border: none; cursor: pointer; padding: 4px 0;
}
.add-prop-btn:hover { text-decoration: underline; }

.state-msg { font-size: 13px; color: #6b7280; padding: 4px 0; }
.state-msg--error { color: #dc2626; }
.state-msg--ok { color: #16a34a; }

.form-actions { display: flex; gap: 8px; justify-content: flex-end; padding-top: 4px; }
.preview-btn, .create-btn {
  padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer;
}
.preview-btn { background: #f3f4f6; color: #1d4ed8; border: 1px solid #bfdbfe; }
.preview-btn:hover:not(:disabled) { background: #eff6ff; }
.create-btn { background: #16a34a; color: white; border: none; }
.create-btn:hover:not(:disabled) { background: #15803d; }
.preview-btn:disabled, .create-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Preview pane */
.preview-title {
  font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  color: #374151; margin-bottom: 12px;
}
.preview-meta { font-size: 12px; color: #6b7280; margin-bottom: 8px; display: flex; flex-direction: column; gap: 2px; }
.preview-path { color: #9ca3af; }
.mono { font-family: monospace; }
.preview-content {
  font-size: 11px; color: #374151; white-space: pre-wrap; max-height: 400px; overflow-y: auto;
  font-family: monospace; margin-top: 12px; background: #f9fafb; border-radius: 6px; padding: 10px;
}
</style>
