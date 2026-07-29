<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { EditorState } from '@codemirror/state'
import { EditorView, basicSetup } from 'codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

interface Props {
  modelValue: string
  readonly?: boolean
  placeholder?: string
  minHeight?: string
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
  placeholder: '',
  minHeight: '200px',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const activeTab = ref<'edit' | 'preview'>('edit')
const mountEl = ref<HTMLDivElement | null>(null)
let editorView: EditorView | null = null
let isSyncingFromProps = false

const buildExtensions = () => {
  const extensions = [
    basicSetup,
    markdown(),
    EditorView.lineWrapping,
    EditorView.updateListener.of((update) => {
      if (!update.docChanged || isSyncingFromProps) return
      emit('update:modelValue', update.state.doc.toString())
    }),
    EditorView.theme({
      '&': {
        minHeight: props.minHeight,
        fontSize: '13px',
      },
      '.cm-scroller': {
        minHeight: props.minHeight,
        fontFamily: "'Cascadia Code', 'Fira Code', monospace",
      },
      '.cm-content': {
        padding: '12px',
      },
      '.cm-focused': {
        outline: 'none',
      },
    }),
  ]
  if (props.readonly) {
    extensions.push(EditorView.editable.of(false))
  }
  return extensions
}

const createEditor = () => {
  if (!mountEl.value) return
  editorView = new EditorView({
    state: EditorState.create({
      doc: props.modelValue,
      extensions: buildExtensions(),
    }),
    parent: mountEl.value,
  })
}

const destroyEditor = () => {
  editorView?.destroy()
  editorView = null
}

const insertAtCursor = (text: string) => {
  if (!editorView) {
    emit('update:modelValue', `${props.modelValue}${text}`)
    return
  }
  const { from, to } = editorView.state.selection.main
  editorView.dispatch({
    changes: { from, to, insert: text },
    selection: { anchor: from + text.length },
  })
  editorView.focus()
}

const focusEditor = () => {
  editorView?.focus()
}

const getCursorOffset = (): number =>
  editorView?.state.selection.main.from ?? props.modelValue.length

watch(() => props.modelValue, (nextValue) => {
  if (!editorView) return
  const currentValue = editorView.state.doc.toString()
  if (currentValue === nextValue) return
  isSyncingFromProps = true
  editorView.dispatch({
    changes: { from: 0, to: currentValue.length, insert: nextValue },
  })
  isSyncingFromProps = false
})

watch(() => props.readonly, () => {
  if (!editorView || !mountEl.value) return
  destroyEditor()
  createEditor()
})

const previewHtml = computed(() =>
  DOMPurify.sanitize(marked.parse(props.modelValue || '') as string),
)

onMounted(createEditor)
onUnmounted(destroyEditor)

defineExpose({
  insertAtCursor,
  focusEditor,
  getCursorOffset,
})
</script>

<template>
  <div class="markdown-editor">
    <div class="markdown-editor__tabs">
      <button
        class="markdown-editor__tab"
        :class="{ 'markdown-editor__tab--active': activeTab === 'edit' }"
        type="button"
        @click="activeTab = 'edit'"
      >
        Edit
      </button>
      <button
        class="markdown-editor__tab"
        :class="{ 'markdown-editor__tab--active': activeTab === 'preview' }"
        type="button"
        @click="activeTab = 'preview'"
      >
        Preview
      </button>
    </div>

    <div
      v-show="activeTab === 'edit'"
      class="markdown-editor__surface"
    >
      <div
        ref="mountEl"
        class="markdown-editor__mount"
        :data-placeholder="placeholder"
      />
    </div>

    <div
      v-show="activeTab === 'preview'"
      class="markdown-editor__preview"
      v-html="previewHtml"
    />
  </div>
</template>

<style scoped>
.markdown-editor {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
  background: white;
}

.markdown-editor__tabs {
  display: flex;
  gap: 2px;
  padding: 6px;
  background: #f8fafc;
  border-bottom: 1px solid #e5e7eb;
}

.markdown-editor__tab {
  border: 0;
  background: transparent;
  color: #64748b;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.markdown-editor__tab--active {
  background: white;
  color: #0f172a;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.markdown-editor__surface,
.markdown-editor__preview {
  min-height: v-bind('props.minHeight');
}

.markdown-editor__mount {
  position: relative;
}

.markdown-editor__mount:empty::before {
  content: attr(data-placeholder);
  position: absolute;
  top: 12px;
  left: 12px;
  color: #94a3b8;
  pointer-events: none;
  font-size: 13px;
}

.markdown-editor__preview {
  padding: 16px;
  color: #1f2937;
  line-height: 1.65;
}

.markdown-editor__preview :deep(h1),
.markdown-editor__preview :deep(h2),
.markdown-editor__preview :deep(h3) {
  margin: 0 0 12px;
  color: #0f172a;
}

.markdown-editor__preview :deep(p),
.markdown-editor__preview :deep(ul),
.markdown-editor__preview :deep(ol) {
  margin: 0 0 12px;
}

.markdown-editor__preview :deep(code) {
  background: #f1f5f9;
  padding: 1px 4px;
  border-radius: 4px;
}
</style>
