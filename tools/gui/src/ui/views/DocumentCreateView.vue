<script setup lang="ts">
import { computed, inject, onMounted, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useWriteBlock } from '../composables/useWriteBlock'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import ArtifactReferenceInput from '../components/ArtifactReferenceInput.vue'
import { draftDocumentPath } from '../lib/referenceLinks.js'
import type { DocumentType } from '../../domain'
import { collectVerificationIssues, readErrorMessage } from '../lib/errors'
import { formatEntityTypeTerm } from '../lib/documentSections'

const svc = inject(modelServiceKey)!
const router = useRouter()
const writeBlocked = useWriteBlock()

const documentTypes = ref<DocumentType[]>([])
const docType = ref('')
const docTypeRaw = ref('')
const title = ref('')
const status = ref('draft')
const keywords = ref('')
const body = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const verificationIssues = ref<string[]>([])
const warnings = ref<string[]>([])
const showReferencePicker = ref(false)
type MarkdownEditorHandle = { insertAtCursor: (markdownLink: string) => void }
const editorRef = ref<MarkdownEditorHandle | null>(null)
const lastAutoBody = ref('')
const bodyWasManuallyEdited = ref(false)
const syncingAutoBody = ref(false)
const titleTouched = ref(false)
const submitAttempted = ref(false)

// Frontmatter field tracking
const headerWasManuallyEdited = ref(false)
const lastAutoFrontmatter = ref<Record<string, string | string[]>>({})
const extraFrontmatter = ref<Record<string, string | string[]>>({})

// Type switch warning dialog
const typeSwitchWarning = ref<string | null>(null)
const pendingDocType = ref<string | null>(null)

const placeholderBody = (requiredSections: readonly string[]) =>
  requiredSections.map((section) => `## ${section}\n\n`).join('\n')

const formatFieldLabel = (name: string) =>
  name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

const selectedType = computed(() =>
  documentTypes.value.find((type) => type.doc_type === docType.value) ?? null,
)

const extraFields = computed(() => selectedType.value?.extra_frontmatter_fields ?? [])
const requiredEntityTypes = computed(() => selectedType.value?.required_entity_type_connections ?? [])
const suggestedEntityTypes = computed(() => selectedType.value?.suggested_entity_type_connections ?? [])
const sectionsWithEntityHints = computed(() =>
  (selectedType.value?.sections ?? []).filter(
    (section) =>
      (section.required_entity_type_connections?.length ?? 0) > 0 ||
      (section.suggested_entity_type_connections?.length ?? 0) > 0,
  ),
)

const draftPath = computed(() => draftDocumentPath(docType.value, selectedType.value?.subdirectory))
const titleError = computed(() =>
  (!title.value.trim() && (titleTouched.value || submitAttempted.value))
    ? 'Title is required.'
    : null,
)

onMounted(() => {
  loading.value = true
  void Effect.runPromise(svc.listDocumentTypes()).then((types) => {
    documentTypes.value = types
    if (!docType.value && types.length > 0) {
      docType.value = types[0].doc_type
      docTypeRaw.value = types[0].doc_type
    }
    loading.value = false
  }).catch((reason: unknown) => {
    error.value = readErrorMessage(reason)
    loading.value = false
  })
})

watch(body, (nextValue) => {
  if (syncingAutoBody.value) return
  bodyWasManuallyEdited.value = nextValue !== lastAutoBody.value
})

watch(extraFrontmatter, (next) => {
  if (syncingAutoBody.value) return
  headerWasManuallyEdited.value = JSON.stringify(next) !== JSON.stringify(lastAutoFrontmatter.value)
}, { deep: true })

watch(title, () => {
  verificationIssues.value = []
})

watch(docTypeRaw, (next) => {
  if (next === docType.value) return
  const dirtyParts = [
    ...(headerWasManuallyEdited.value ? ['header fields'] : []),
    ...(bodyWasManuallyEdited.value ? ['body'] : []),
  ]
  if (dirtyParts.length > 0) {
    typeSwitchWarning.value = `Switching type will reset your edited ${dirtyParts.join(' and ')}.`
    pendingDocType.value = next
    void nextTick(() => { docTypeRaw.value = docType.value })
  } else {
    docType.value = next
  }
})

watch(selectedType, (type) => {
  if (!type) return
  const nextBody = placeholderBody(type.required_sections)
  if (!headerWasManuallyEdited.value && !bodyWasManuallyEdited.value) {
    syncingAutoBody.value = true
    // Reset body
    body.value = nextBody
    lastAutoBody.value = nextBody
    bodyWasManuallyEdited.value = false
    // Reset frontmatter
    const defaults: Record<string, string | string[]> = {}
    for (const f of type.extra_frontmatter_fields ?? []) {
      defaults[f.name] = f.field_type === 'array' ? [] : ''
    }
    extraFrontmatter.value = { ...defaults }
    lastAutoFrontmatter.value = { ...defaults }
    headerWasManuallyEdited.value = false
    syncingAutoBody.value = false
  }
})

const onArrayFieldInput = (fieldName: string, raw: string) => {
  extraFrontmatter.value[fieldName] = raw.split(',').map(v => v.trim()).filter(Boolean)
  headerWasManuallyEdited.value = true
}

const buildExtraFrontmatter = (): Record<string, unknown> | undefined => {
  const result: Record<string, unknown> = {}
  for (const f of extraFields.value) {
    const v = extraFrontmatter.value[f.name]
    if (Array.isArray(v) && v.length > 0) result[f.name] = v
    else if (typeof v === 'string' && v.trim()) result[f.name] = v.trim()
  }
  return Object.keys(result).length > 0 ? result : undefined
}

const confirmTypeSwitch = () => {
  if (!pendingDocType.value) return
  headerWasManuallyEdited.value = false
  bodyWasManuallyEdited.value = false
  docType.value = pendingDocType.value
  docTypeRaw.value = pendingDocType.value
  typeSwitchWarning.value = null
  pendingDocType.value = null
}

const cancelTypeSwitch = () => {
  typeSwitchWarning.value = null
  pendingDocType.value = null
  docTypeRaw.value = docType.value
}

const resetAll = () => {
  headerWasManuallyEdited.value = false
  bodyWasManuallyEdited.value = false
  const current = docType.value
  docType.value = ''
  void nextTick(() => { docType.value = current })
}

const submit = () => {
  submitAttempted.value = true
  titleTouched.value = true
  verificationIssues.value = []
  warnings.value = []
  if (titleError.value) return
  error.value = null
  saving.value = true
  void Effect.runPromise(svc.createDocument({
    doc_type: docType.value,
    title: title.value,
    body: body.value,
    keywords: keywords.value.split(',').map((value) => value.trim()).filter(Boolean),
    status: status.value,
    extra_frontmatter: buildExtraFrontmatter(),
    dry_run: false,
  })).then((result) => {
    if (!result.wrote) {
      verificationIssues.value = collectVerificationIssues(result.verification)
      warnings.value = [...(result.warnings ?? [])]
      error.value = verificationIssues.value.length
        ? 'Document could not be created until the validation issues are fixed.'
        : 'Document could not be created.'
      saving.value = false
      return
    }
    saving.value = false
    void router.push(`/documents/${result.artifact_id}`)
  }).catch((reason: unknown) => {
    error.value = readErrorMessage(reason)
    saving.value = false
  })
}

const insertReference = (markdownLink: string) => {
  editorRef.value?.insertAtCursor(markdownLink)
}
</script>

<template>
  <div class="create-page">
    <div class="page-header">
      <button
        class="back-link"
        type="button"
        @click="router.push('/documents')"
      >
        ← Documents
      </button>
      <h1 class="page-title">
        New Document
      </h1>
    </div>

    <div
      v-if="loading"
      class="state-msg"
    >
      Loading…
    </div>
    <div
      v-else
      class="card"
    >
      <div class="form-grid">
        <label class="form-field">
          <span>Document Type</span>
          <select
            v-model="docTypeRaw"
            class="form-control"
          >
            <option
              v-for="type in documentTypes"
              :key="type.doc_type"
              :value="type.doc_type"
            >{{ type.name }}</option>
          </select>
        </label>

        <label class="form-field">
          <span>Status</span>
          <select
            v-model="status"
            class="form-control"
          >
            <option value="draft">draft</option>
            <option value="accepted">accepted</option>
            <option value="rejected">rejected</option>
            <option value="superseded">superseded</option>
          </select>
        </label>
      </div>

      <div
        v-if="typeSwitchWarning"
        class="type-switch-warning"
      >
        {{ typeSwitchWarning }}
        <button
          class="link-btn warn"
          @click="confirmTypeSwitch"
        >
          Switch anyway
        </button>
        <button
          class="link-btn"
          @click="cancelTypeSwitch"
        >
          Keep editing
        </button>
      </div>
      <div
        v-else-if="headerWasManuallyEdited || bodyWasManuallyEdited"
        class="dirty-hint"
      >
        Document type cannot be changed after editing —
        <button
          class="link-btn"
          @click="resetAll"
        >
          clear all
        </button> to reset.
      </div>

      <label class="form-field">
        <span>Title *</span>
        <input
          v-model="title"
          class="form-control"
          :class="{ 'form-control--invalid': titleError }"
          type="text"
          placeholder="Use concise, decision-oriented wording"
          @blur="titleTouched = true"
        >
        <div
          v-if="titleError"
          class="field-error"
        >{{ titleError }}</div>
      </label>

      <label class="form-field">
        <span>Keywords</span>
        <input
          v-model="keywords"
          class="form-control"
          type="text"
          placeholder="Comma-separated terms"
        >
      </label>

      <template
        v-for="field in extraFields"
        :key="field.name"
      >
        <label class="form-field">
          <span>{{ formatFieldLabel(field.name) }}{{ field.required ? ' *' : '' }}</span>
          <input
            v-if="field.field_type === 'array'"
            :value="(extraFrontmatter[field.name] as string[] || []).join(', ')"
            class="form-control"
            type="text"
            placeholder="Comma-separated values"
            @input="onArrayFieldInput(field.name, ($event.target as HTMLInputElement).value)"
          >
          <input
            v-else
            v-model="(extraFrontmatter as any)[field.name]"
            class="form-control"
            :type="field.name === 'date' ? 'date' : 'text'"
            @input="headerWasManuallyEdited = true"
          >
        </label>
      </template>

      <div
        v-if="requiredEntityTypes.length"
        class="entity-connection-hint entity-connection-hint--required"
      >
        <strong>Required entity links:</strong>
        Link at least one matching entity for each term:
        <span
          v-for="(t, i) in requiredEntityTypes"
          :key="t"
          class="entity-type-tag entity-type-tag--required"
          :title="t"
        >{{ formatEntityTypeTerm(t) }}<span v-if="i < requiredEntityTypes.length - 1">,&nbsp;</span></span>
      </div>
      <div
        v-if="suggestedEntityTypes.length"
        class="entity-connection-hint entity-connection-hint--suggested"
      >
        <strong>Suggested entity links:</strong>
        Consider linking matching entities for:
        <span
          v-for="(t, i) in suggestedEntityTypes"
          :key="t"
          class="entity-type-tag"
          :title="t"
        >{{ formatEntityTypeTerm(t) }}<span v-if="i < suggestedEntityTypes.length - 1">,&nbsp;</span></span>
      </div>

      <div
        v-if="sectionsWithEntityHints.length"
        class="section-hints"
      >
        <div
          v-for="section in sectionsWithEntityHints"
          :key="section.name"
          class="section-hint"
        >
          <span class="section-hint__name"># {{ section.name }}</span>
          <span
            v-if="section.required_entity_type_connections?.length"
            class="entity-connection-hint entity-connection-hint--required entity-connection-hint--inline"
          >
            Required:
            <span
              v-for="(t, i) in section.required_entity_type_connections"
              :key="t"
              class="entity-type-tag entity-type-tag--required"
              :title="t"
            >{{ formatEntityTypeTerm(t) }}<span v-if="i < section.required_entity_type_connections.length - 1">,&nbsp;</span></span>
          </span>
          <span
            v-if="section.suggested_entity_type_connections?.length"
            class="entity-connection-hint entity-connection-hint--suggested entity-connection-hint--inline"
          >
            Suggested:
            <span
              v-for="(t, i) in section.suggested_entity_type_connections"
              :key="t"
              class="entity-type-tag"
              :title="t"
            >{{ formatEntityTypeTerm(t) }}<span v-if="i < section.suggested_entity_type_connections.length - 1">,&nbsp;</span></span>
          </span>
        </div>
      </div>

      <div class="form-field">
        <span>Body</span>
        <div class="editor-toolbar">
          <button
            class="secondary-btn"
            type="button"
            @click="showReferencePicker = true"
          >
            Insert Reference
          </button>
        </div>
        <MarkdownEditor
          ref="editorRef"
          v-model="body"
          min-height="360px"
          placeholder="Write markdown content..."
        />
      </div>

      <div
        v-if="warnings.length"
        class="warnings-block"
      >
        <div
          v-for="w in warnings"
          :key="w"
          class="warn"
        >
          {{ w }}
        </div>
      </div>

      <div
        v-if="error"
        class="state-msg state-msg--error"
      >
        {{ error }}
      </div>
      <ul
        v-if="verificationIssues.length"
        class="issue-list"
      >
        <li
          v-for="issue in verificationIssues"
          :key="issue"
        >
          {{ issue }}
        </li>
      </ul>

      <div class="actions">
        <button
          class="submit-btn"
          type="button"
          :disabled="saving || !docType || writeBlocked"
          :title="writeBlocked ? 'Write operations are temporarily blocked' : ''"
          @click="submit"
        >
          Create Document
        </button>
      </div>
    </div>

    <div
      v-if="showReferencePicker"
      class="overlay"
      @click.self="showReferencePicker = false"
    >
      <ArtifactReferenceInput
        :current-path="draftPath"
        @insert="insertReference"
        @close="showReferencePicker = false"
      />
    </div>
  </div>
</template>

<style scoped>
.create-page { max-width: 980px; margin: 0 auto; }
.page-header { display: flex; gap: 16px; align-items: center; margin-bottom: 20px; }
.back-link { border: 0; background: transparent; color: #64748b; cursor: pointer; padding: 0; font-size: 13px; }
.page-title { font-size: 22px; font-weight: 600; }
.card { background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.form-field span { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700; }
.form-control {
  padding: 9px 11px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 13px;
}
.form-control--invalid {
  border-color: #dc2626;
  background: #fef2f2;
}
.field-error {
  color: #dc2626;
  font-size: 12px;
}
.editor-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.secondary-btn {
  border: 0;
  background: #e2e8f0;
  color: #0f172a;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.actions { display: flex; justify-content: flex-end; }
.submit-btn {
  border: 0;
  background: #2563eb;
  color: white;
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.state-msg { color: #64748b; margin-bottom: 12px; }
.state-msg--error { color: #dc2626; }
.warnings-block { margin-bottom: 12px; }
.warn { font-size: 12px; color: #b45309; margin-bottom: 4px; }
.issue-list {
  margin: 0 0 12px;
  padding-left: 18px;
  color: #991b1b;
  font-size: 13px;
}
.overlay {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(15, 23, 42, 0.3);
  padding: 16px;
}

.type-switch-warning {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #92400e;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.dirty-hint {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 10px;
}

.link-btn {
  border: none;
  background: none;
  cursor: pointer;
  color: #2563eb;
  font-size: 12px;
  padding: 0;
  text-decoration: underline;
}

.link-btn.warn {
  color: #b45309;
}

.link-btn:hover {
  opacity: 0.8;
}

.entity-connection-hint {
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  margin-bottom: 10px;
  line-height: 1.6;
}
.entity-connection-hint--required {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
}
.entity-connection-hint--suggested {
  background: #eff6ff;
  border: 1px solid #93c5fd;
  color: #1e40af;
}
.entity-type-tag {
  font-family: monospace;
  font-size: 11px;
  background: rgba(0, 0, 0, .06);
  border-radius: 3px;
  padding: 1px 4px;
}
.entity-type-tag--required {
  background: rgba(220, 38, 38, .1);
}

.section-hints {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 14px;
  background: #f8fafc;
}
.section-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.section-hint + .section-hint {
  border-top: 1px solid #e5e7eb;
}
.section-hint__name {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
}
.entity-connection-hint--inline {
  margin-bottom: 0;
  padding: 2px 8px;
}

@media (max-width: 700px) {
  .form-grid { grid-template-columns: 1fr; }
  .type-switch-warning { flex-direction: column; align-items: flex-start; gap: 8px; }
}
</style>
