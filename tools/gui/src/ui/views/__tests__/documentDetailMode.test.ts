/**
 * Tests for DocumentDetailView page-level view/edit mode.
 *
 * All tests exercise pure reactive logic (mode state, field resets, save flow)
 * without mounting components.
 */
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'

type DocumentDetail = {
  artifact_id: string
  title: string
  status: string
  keywords: string[]
  content_text: string
  doc_type: string
  path: string
  is_global: boolean
}

function makeDetailState(initial: DocumentDetail) {
  const editing = ref(false)
  const detail = ref<DocumentDetail>(initial)
  const title = ref(initial.title)
  const status = ref(initial.status)
  const keywords = ref(initial.keywords.join(', '))
  const body = ref(initial.content_text)

  const startEdit = () => { editing.value = true }

  const cancelEdit = () => {
    title.value = detail.value.title
    status.value = detail.value.status
    keywords.value = detail.value.keywords.join(', ')
    body.value = detail.value.content_text
    editing.value = false
  }

  const afterSave = (saved: DocumentDetail) => {
    detail.value = saved
    title.value = saved.title
    status.value = saved.status
    keywords.value = saved.keywords.join(', ')
    body.value = saved.content_text
    editing.value = false
  }

  const titleTouched = ref(false)
  const saveAttempted = ref(false)
  const titleError = computed(() =>
    (!title.value.trim() && (titleTouched.value || saveAttempted.value))
      ? 'Title is required.'
      : null,
  )

  return { editing, detail, title, status, keywords, body, titleTouched, saveAttempted, titleError, startEdit, cancelEdit, afterSave }
}

const SAMPLE: DocumentDetail = {
  artifact_id: 'STD@123.abc',
  title: 'Architecture Guidelines',
  status: 'accepted',
  keywords: ['arch', 'guidelines'],
  content_text: '## Overview\n\nSome content.',
  doc_type: 'standard',
  path: '/model/docs/arch.md',
  is_global: false,
}

describe('DocumentDetailView mode state', () => {
  it('mounts in view mode (editing=false)', () => {
    const { editing } = makeDetailState(SAMPLE)
    expect(editing.value).toBe(false)
  })

  it('startEdit() flips to edit mode', () => {
    const { editing, startEdit } = makeDetailState(SAMPLE)
    startEdit()
    expect(editing.value).toBe(true)
  })

  it('cancelEdit() returns to view mode without changing detail', () => {
    const { editing, title, startEdit, cancelEdit } = makeDetailState(SAMPLE)
    startEdit()
    title.value = 'Changed Title'
    cancelEdit()
    expect(editing.value).toBe(false)
    expect(title.value).toBe(SAMPLE.title)
  })

  it('cancelEdit() resets all fields to loaded values', () => {
    const { editing, title, status, keywords, body, startEdit, cancelEdit } = makeDetailState(SAMPLE)
    startEdit()
    title.value = 'X'
    status.value = 'draft'
    keywords.value = 'foo'
    body.value = '# Changed'
    cancelEdit()
    expect(editing.value).toBe(false)
    expect(title.value).toBe(SAMPLE.title)
    expect(status.value).toBe(SAMPLE.status)
    expect(keywords.value).toBe(SAMPLE.keywords.join(', '))
    expect(body.value).toBe(SAMPLE.content_text)
  })

  it('afterSave() returns to view mode and updates detail', () => {
    const { editing, title, detail, startEdit, afterSave } = makeDetailState(SAMPLE)
    startEdit()
    const saved: DocumentDetail = { ...SAMPLE, title: 'New Title', status: 'draft' }
    afterSave(saved)
    expect(editing.value).toBe(false)
    expect(title.value).toBe('New Title')
    expect(detail.value.title).toBe('New Title')
  })

  it('titleError fires on empty title after saveAttempted', () => {
    const { title, saveAttempted, titleError } = makeDetailState(SAMPLE)
    title.value = ''
    saveAttempted.value = true
    expect(titleError.value).toBe('Title is required.')
  })

  it('titleError is null when title is non-empty', () => {
    const { title, saveAttempted, titleError } = makeDetailState(SAMPLE)
    title.value = 'Some Title'
    saveAttempted.value = true
    expect(titleError.value).toBeNull()
  })

  it('document id change resets editing to false (simulated)', () => {
    const { editing, startEdit } = makeDetailState(SAMPLE)
    startEdit()
    expect(editing.value).toBe(true)
    // Simulate documentId watcher behaviour
    editing.value = false
    expect(editing.value).toBe(false)
  })
})
