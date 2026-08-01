<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import { renderMarkdown } from '../../application/MarkdownService'
import { modelServiceKey, toastKey } from '../keys'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import ArtifactReferenceInput from '../components/ArtifactReferenceInput.vue'
import type { DocumentDetail, DocumentType } from '../../domain'
import { collectVerificationIssues, readErrorMessage } from '../lib/errors'
import { routeInternalLinkClicks } from '../lib/internalLinkClicks'
import { findSectionSpec, sectionAtOffset, sectionEntityTypeTerms } from '../lib/documentSections'

const svc = inject(modelServiceKey)!
const addToast = inject(toastKey)!
const route = useRoute()
const router = useRouter()

const documentId = computed(() => route.params.artifactId as string)
const detail = ref<DocumentDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const error = ref<string | null>(null)
const verificationIssues = ref<string[]>([])
const showReferencePicker = ref(false)
type MarkdownEditorHandle = {
  insertAtCursor: (markdownLink: string) => void
  getCursorOffset: () => number
}
const editorRef = ref<MarkdownEditorHandle | null>(null)
const isGlobalDocument = computed(() => detail.value?.is_global ?? false)
const documentTypes = ref<DocumentType[]>([])
const referenceCursorOffset = ref(0)

const editing = ref(false)

const title = ref('')
const status = ref('draft')
const keywords = ref('')
const body = ref('')
const titleTouched = ref(false)
const saveAttempted = ref(false)
const titleError = computed(() =>
  (!title.value.trim() && (titleTouched.value || saveAttempted.value))
    ? 'Title is required.'
    : null,
)

const previewHtml = computed(() => renderMarkdown(body.value || '', 'docs'))
const onBodyClick = routeInternalLinkClicks(router)

const load = async () => {
  loading.value = true
  error.value = null
  verificationIssues.value = []
  try {
    const doc = await Effect.runPromise(svc.getDocument(documentId.value))
    detail.value = doc
    title.value = doc.title
    status.value = doc.status
    keywords.value = (doc.keywords ?? []).join(', ')
    body.value = doc.content_text ?? ''
  } catch (reason: unknown) {
    error.value = readErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  void Effect.runPromise(svc.listDocumentTypes())
    .then((types) => { documentTypes.value = types })
    .catch((reason: unknown) => {
      console.error('Failed to load document types', readErrorMessage(reason))
    })
})
watch(documentId, () => {
  editing.value = false
  void load()
})

const matchedDocType = computed(() =>
  documentTypes.value.find((type) => type.doc_type === detail.value?.doc_type) ?? null,
)

const currentSectionName = computed(() => sectionAtOffset(body.value, referenceCursorOffset.value))

const currentSectionSpec = computed(() =>
  findSectionSpec(matchedDocType.value?.sections, currentSectionName.value),
)

const suggestedEntityTypesForSection = computed(() => sectionEntityTypeTerms(currentSectionSpec.value))

const openReferencePicker = () => {
  referenceCursorOffset.value = editorRef.value?.getCursorOffset() ?? body.value.length
  showReferencePicker.value = true
}

const startEdit = () => {
  error.value = null
  verificationIssues.value = []
  titleTouched.value = false
  saveAttempted.value = false
  editing.value = true
}

const cancelEdit = () => {
  if (detail.value) {
    title.value = detail.value.title
    status.value = detail.value.status
    keywords.value = (detail.value.keywords ?? []).join(', ')
    body.value = detail.value.content_text ?? ''
  }
  error.value = null
  verificationIssues.value = []
  editing.value = false
}

const save = async () => {
  saveAttempted.value = true
  titleTouched.value = true
  verificationIssues.value = []
  if (titleError.value) return
  saving.value = true
  error.value = null
  try {
    const result = await Effect.runPromise(svc.editDocument(documentId.value, {
      title: title.value,
      status: status.value,
      keywords: keywords.value.split(',').map((value) => value.trim()).filter(Boolean),
      body: body.value,
      dry_run: false,
    }))
    if (!result.wrote) {
      verificationIssues.value = collectVerificationIssues(result.verification)
      error.value = verificationIssues.value.length
        ? 'Document could not be saved until the validation issues are fixed.'
        : 'Document could not be saved.'
      return
    }
    addToast('Document saved')
    editing.value = false
    await load()
  } catch (reason: unknown) {
    error.value = readErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

const remove = async () => {
  if (!window.confirm(`Delete document ${documentId.value}?`)) return
  deleting.value = true
  error.value = null
  try {
    await Effect.runPromise(svc.deleteDocument(documentId.value))
    void router.push('/documents')
  } catch (reason: unknown) {
    error.value = readErrorMessage(reason)
  } finally {
    deleting.value = false
  }
}

const insertReference = (markdownLink: string) => {
  editorRef.value?.insertAtCursor(markdownLink)
}
</script>

<template>
  <div class="detail-page">
    <div class="page-header">
      <button
        class="back-link"
        type="button"
        @click="router.push('/documents')"
      >
        ← Documents
      </button>
      <div class="page-actions">
        <RouterLink
          v-if="detail && !isGlobalDocument"
          :to="{ path: '/promote', query: { document_id: detail.artifact_id } }"
          class="secondary-btn"
        >
          ↑ Promote to Enterprise
        </RouterLink>
        <template v-if="!editing">
          <button
            class="primary-btn"
            type="button"
            :disabled="loading"
            @click="startEdit"
          >
            Edit
          </button>
          <button
            class="danger-btn"
            type="button"
            :disabled="deleting || loading"
            @click="remove"
          >
            Delete
          </button>
        </template>
        <template v-else>
          <button
            class="primary-btn"
            type="button"
            :disabled="saving || loading"
            @click="save"
          >
            Save
          </button>
          <button
            class="secondary-btn"
            type="button"
            :disabled="saving"
            @click="cancelEdit"
          >
            Cancel
          </button>
        </template>
      </div>
    </div>

    <div
      v-if="loading"
      class="state-msg"
    >
      Loading…
    </div>
    <div
      v-else-if="error && !detail"
      class="state-msg state-msg--error"
    >
      {{ error }}
    </div>

    <!-- View mode -->
    <div
      v-else-if="detail && !editing"
      class="card"
    >
      <div class="view-header">
        <h1 class="doc-title">
          {{ detail.title }}
        </h1>
        <div class="view-pills">
          <span class="readonly-pill readonly-pill--type">{{ detail.doc_type }}</span>
          <span class="readonly-pill readonly-pill--status">{{ detail.status }}</span>
        </div>
      </div>
      <div
        v-if="detail.keywords?.length"
        class="view-keywords"
      >
        <span
          v-for="kw in detail.keywords"
          :key="kw"
          class="keyword-chip"
        >{{ kw }}</span>
      </div>
      <div
        class="doc-body"
        @click="onBodyClick"
        v-html="previewHtml"
      />
      <div class="artifact-meta">
        <code>{{ detail.artifact_id }}</code>
        <code>{{ detail.path }}</code>
      </div>
    </div>

    <!-- Edit mode -->
    <div
      v-else-if="detail && editing"
      class="card"
    >
      <div class="meta-grid">
        <label class="form-field form-field--wide">
          <span>Title *</span>
          <input
            v-model="title"
            class="form-control"
            :class="{ 'form-control--invalid': titleError }"
            type="text"
            @blur="titleTouched = true"
          >
          <div
            v-if="titleError"
            class="field-error"
          >
            {{ titleError }}
          </div>
        </label>

        <div class="form-field">
          <span>Type</span>
          <div class="readonly-pill">
            {{ detail.doc_type }}
          </div>
        </div>

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

      <label class="form-field">
        <span>Keywords</span>
        <input
          v-model="keywords"
          class="form-control"
          type="text"
        >
      </label>

      <div class="form-field">
        <span>Body</span>
        <div class="editor-toolbar">
          <button
            class="secondary-btn"
            type="button"
            @click="openReferencePicker"
          >
            Insert Reference
          </button>
        </div>
        <MarkdownEditor
          ref="editorRef"
          v-model="body"
          min-height="420px"
          placeholder="Document markdown..."
        />
      </div>

      <div class="artifact-meta">
        <code>{{ detail.artifact_id }}</code>
        <code>{{ detail.path }}</code>
      </div>

      <div class="bottom-actions">
        <button
          class="secondary-btn"
          type="button"
          :disabled="saving"
          @click="cancelEdit"
        >
          Cancel
        </button>
        <button
          class="primary-btn"
          type="button"
          :disabled="saving || loading"
          @click="save"
        >
          Save
        </button>
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
    </div>

    <div
      v-if="showReferencePicker && editing"
      class="overlay"
      @click.self="showReferencePicker = false"
    >
      <ArtifactReferenceInput
        :current-path="detail?.path"
        :section-label="currentSectionName ?? undefined"
        :suggested-entity-types="suggestedEntityTypesForSection"
        @insert="insertReference"
        @close="showReferencePicker = false"
      />
    </div>
  </div>
</template>

<style scoped>
.detail-page { max-width: 1100px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; }
.back-link { border: 0; background: transparent; color: #64748b; cursor: pointer; padding: 0; font-size: 13px; }
.page-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.card { background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; }
.meta-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.form-field--wide { grid-column: span 1; }
.form-field span { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700; }
.form-control { padding: 9px 11px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; }
.form-control--invalid { border-color: #dc2626; background: #fef2f2; }
.field-error { color: #dc2626; font-size: 12px; }
.readonly-pill {
  display: inline-flex; align-items: center; min-height: 39px; padding: 0 11px;
  border-radius: 8px; background: #eff6ff; color: #1d4ed8; font-size: 13px; font-weight: 600;
}
.readonly-pill--type { background: #eff6ff; color: #1d4ed8; }
.readonly-pill--status { background: #f0fdf4; color: #166534; min-height: unset; padding: 3px 10px; }
.editor-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.artifact-meta { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; color: #64748b; font-size: 12px; }
.bottom-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.primary-btn, .secondary-btn, .danger-btn {
  border: 0; border-radius: 8px; padding: 9px 14px;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.primary-btn { background: #2563eb; color: white; }
.secondary-btn { background: #e2e8f0; color: #0f172a; }
.danger-btn { background: #fee2e2; color: #991b1b; }
.state-msg { color: #64748b; }
.state-msg--error { color: #dc2626; margin-top: 10px; }
.issue-list { margin: 10px 0 0; padding-left: 18px; color: #991b1b; font-size: 13px; }
.overlay {
  position: fixed; inset: 0; display: grid; place-items: center;
  background: rgba(15, 23, 42, 0.3); padding: 16px;
}
/* View mode styles */
.view-header { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 12px; }
.doc-title { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0; flex: 1; }
.view-pills { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }
.view-keywords { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.keyword-chip {
  background: #f1f5f9; color: #475569; border-radius: 6px;
  padding: 2px 9px; font-size: 12px; font-weight: 500;
}
.doc-body {
  color: #1f2937; line-height: 1.65; font-size: 14px;
  border-top: 1px solid #e5e7eb; padding-top: 16px; margin-top: 4px;
}
.doc-body :deep(h1), .doc-body :deep(h2), .doc-body :deep(h3) { margin: 0 0 12px; color: #0f172a; }
.doc-body :deep(p), .doc-body :deep(ul), .doc-body :deep(ol) { margin: 0 0 12px; }
.doc-body :deep(code) { background: #f1f5f9; padding: 1px 4px; border-radius: 4px; }
.doc-body :deep(pre) { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; overflow-x: auto; }
@media (max-width: 760px) { .meta-grid { grid-template-columns: 1fr; } }
</style>
