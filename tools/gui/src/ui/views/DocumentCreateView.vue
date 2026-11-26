<script setup lang="ts">
import { computed, inject, onMounted, ref, watch, nextTick } from 'vue'
import { csvToList } from '../lib/commaList'
import { documentTypeFor, titleErrorFor } from '../lib/documentForms'
import {
  filledExtraFrontmatter,
  formatFieldLabel,
  placeholderBody,
  sectionsWithLinkHints as sectionsWithLinkHintsOf,
} from './DocumentCreateView.helpers'
import { useRouter } from 'vue-router'
import DocumentHomeSelect from '../components/DocumentHomeSelect.vue'
import { homeForCreate } from '../components/ArtifactHomeSelect.helpers'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useCan } from '../composables/usePermissions'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import ArtifactReferenceInput from '../components/ArtifactReferenceInput.vue'
import { draftDocumentPath } from '../lib/referenceLinks.js'
import type { DocumentType } from '../../domain'
import { collectVerificationIssues, readErrorMessage } from '../lib/errors'
import ReferenceTermChips from '../components/ReferenceTermChips.vue'

const svc = inject(modelServiceKey)!
const router = useRouter()
const home = ref('')
const mayCreate = useCan('documents_create_document')

const documentTypes = ref<DocumentType[]>([])
const docType = ref('')
const docTypeRaw = ref('')
const title = ref('')
const status = ref('draft')
const keywords = ref('')
const body = ref('')
const loading = ref(true)  // a view that loads on mount is loading from its first frame, not after it
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

const selectedType = computed(() =>
  documentTypeFor(documentTypes.value, docType.value),
)

const extraFields = computed(() => selectedType.value?.extra_frontmatter_fields ?? [])
const requiredTerms = computed(() => selectedType.value?.required_connections ?? [])
const suggestedTerms = computed(() => selectedType.value?.suggested_connections ?? [])
const sectionsWithLinkHints = computed(() => sectionsWithLinkHintsOf(selectedType.value))

const draftPath = computed(() => draftDocumentPath(docType.value, selectedType.value?.subdirectory))
const titleError = computed(() => titleErrorFor(title.value, titleTouched.value, submitAttempted.value))

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
  extraFrontmatter.value[fieldName] = csvToList(raw)
  headerWasManuallyEdited.value = true
}

const buildExtraFrontmatter = () => filledExtraFrontmatter(extraFields.value, extraFrontmatter.value)

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
    group: homeForCreate(home.value),
    body: body.value,
    keywords: csvToList(keywords.value),
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

        <DocumentHomeSelect v-model="home" />

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

      <p
        v-if="selectedType?.attribution"
        class="section-hint__name"
      >
        {{ selectedType.attribution }}
      </p>

      <div
        v-if="requiredTerms.length"
        class="entity-connection-hint entity-connection-hint--required"
      >
        <strong>Required links:</strong> link at least one match for each term:
        <ReferenceTermChips
          :terms="requiredTerms"
          :document-types="documentTypes"
          required
        />
      </div>
      <div
        v-if="suggestedTerms.length"
        class="entity-connection-hint entity-connection-hint--suggested"
      >
        <strong>Suggested links:</strong> consider linking a match for:
        <ReferenceTermChips
          :terms="suggestedTerms"
          :document-types="documentTypes"
        />
      </div>

      <div
        v-if="sectionsWithLinkHints.length"
        class="section-hints"
      >
        <div
          v-for="section in sectionsWithLinkHints"
          :key="section.name"
          class="section-hint"
        >
          <span class="section-hint__name"># {{ section.name }}</span>
          <span
            v-if="section.required_connections?.length"
            class="entity-connection-hint entity-connection-hint--required entity-connection-hint--inline"
          >
            Required:
            <ReferenceTermChips
              :terms="section.required_connections"
              :document-types="documentTypes"
              required
            />
          </span>
          <span
            v-if="section.suggested_connections?.length"
            class="entity-connection-hint entity-connection-hint--suggested entity-connection-hint--inline"
          >
            Suggested:
            <ReferenceTermChips
              :terms="section.suggested_connections"
              :document-types="documentTypes"
            />
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
          :disabled="saving || !docType || !mayCreate.allowed"
          :title="mayCreate.allowed ? '' : mayCreate.reason"
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
.back-link { border: 0; background: transparent; color: var(--muted); cursor: pointer; padding: 0; font-size: 13px; }
.page-title { font-size: 22px; font-weight: 600; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.form-field span { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700; }
.form-control {
  padding: 9px 11px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 13px;
}
.form-control--invalid {
  border-color: var(--danger);
  background: var(--danger-soft);
}
.field-error {
  color: var(--danger);
  font-size: 12px;
}
.editor-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.secondary-btn {
  border: 0;
  background: var(--border);
  color: var(--text);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.actions { display: flex; justify-content: flex-end; }
.submit-btn {
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.state-msg { color: var(--muted); margin-bottom: 12px; }
.state-msg--error { color: var(--danger); }
.warnings-block { margin-bottom: 12px; }
.warn { font-size: 12px; color: var(--warn-text); margin-bottom: 4px; }
.issue-list {
  margin: 0 0 12px;
  padding-left: 18px;
  color: var(--danger-strong);
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
  background: var(--warn-soft);
  border: 1px solid var(--warn);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--warn-text);
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.dirty-hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}

.link-btn {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--accent);
  font-size: 12px;
  padding: 0;
  text-decoration: underline;
}

.link-btn.warn {
  color: var(--warn-text);
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
  background: var(--danger-soft);
  border: 1px solid var(--danger-border);
  color: var(--danger-strong);
}
.entity-connection-hint--suggested {
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  color: var(--type-text);
}
.section-hints {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 14px;
  background: var(--canvas);
}
.section-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.section-hint + .section-hint {
  border-top: 1px solid var(--border);
}
.section-hint__name {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-2);
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
