<script setup lang="ts">
/**
 * One scratchpad, open for editing.
 *
 * The view owns what the canvas deliberately does not: the document, its undo history, and when a
 * change is worth writing. Keeping the save policy here rather than in a pointer handler is what
 * makes "at most one write a second" a property with a test, rather than an emergent behaviour of
 * whichever gesture fired last.
 */
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, onBeforeRouteLeave } from 'vue-router'
import { Exit } from 'effect'
import ScratchpadCanvas from '../components/ScratchpadCanvas.vue'
import { modelServiceKey } from '../keys'
import { useMutation } from '../composables/useMutation'
import { useQuery } from '../composables/useQuery'
import { useDebouncedScratchpadSave } from '../composables/useDebouncedScratchpadSave'
import EntityPickerInput from '../components/EntityPickerInput.vue'
import ScratchpadNotePanel from '../components/ScratchpadNotePanel.vue'
import { useScratchpadDocument } from '../composables/useScratchpadDocument'
import {
  toReplacePayload,
  withBinding,
  withLink,
  withLinkType,
  withNote,
  withNoteAt,
  withReversedLink,
  withType,
  withoutBinding,
  withoutNote,
  withoutRealization,
  withoutType,
} from '../composables/scratchpadEdits'
import type { Scratchpad } from '../../domain/schemas/scratchpads'
import type { EntityDisplayInfo } from '../../domain'
import type { RepoError } from '../../ports/repositoryErrors'
import type { NotFoundError } from '../../domain'
import type { MarkdownError } from '../../application/MarkdownService'

const route = useRoute()
const svc = inject(modelServiceKey)!
const artifactId = computed(() => String(route.params.artifactId ?? ''))

const document = useScratchpadDocument()
const loadQuery = useQuery<Scratchpad, RepoError | NotFoundError | MarkdownError>()
const saveMutation = useMutation<Scratchpad, RepoError>()
const selectedId = ref<string | null>(null)

/** Ids are minted client-side and are scratchpad-local, which is exactly why they can be: a note id
 * means nothing outside its scratchpad, so no global namespace has to accept it and no round trip
 * is needed before a note can be drawn. */
const mintId = (prefix: string): string =>
  `${prefix}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

const save = async (): Promise<void> => {
  const current = document.current.value
  if (!current) return
  const exit = await saveMutation.run(svc.replaceScratchpad(artifactId.value, {
    version: current.version,
    group: current.group,
    scratchpad: toReplacePayload(current),
  }))
  // The server's answer is adopted rather than merged: it carries the new version, which the next
  // save must send, and a merge would let a stale one through.
  if (Exit.isSuccess(exit)) document.adopt(exit.value)
  else throw new Error(saveMutation.errorMessage.value ?? 'The scratchpad could not be saved.')
}

const saver = useDebouncedScratchpadSave(save)

const edit = (next: Scratchpad): void => {
  document.commit(next)
  saver.schedule()
}

// `useQuery.run` writes into the handle rather than returning; the document adopts what lands.
const load = (): void => { loadQuery.run(svc.getScratchpad(artifactId.value)) }

watch(() => loadQuery.data.value, (loaded) => { if (loaded) document.adopt(loaded) })
onMounted(load)

// A save in flight must not be abandoned by leaving the page: "saved when you stop touching it"
// cannot have an exception for navigating away.
onBeforeRouteLeave(async () => { await saver.flush() })
onBeforeUnmount(() => { void saver.flush() })

const onCreateNote = ({ x, y }: { x: number; y: number }): void => {
  const current = document.current.value
  if (!current) return
  const id = mintId('n')
  const blank = { id, title: 'New note', area: 'unfiled', body: '', destination: 'undecided' } as const
  edit(withNoteAt(withNote(current, blank), id, x, y))
  selectedId.value = id
  // Focus the title so a new note opens ready to be written, which is the whole gesture.
  requestAnimationFrame(() => {
    const field = window.document.querySelector<HTMLElement>(`[data-note-title="${id}"]`)
    field?.focus()
    if (field) window.getSelection()?.selectAllChildren(field)
  })
}

const onMoveNote = ({ id, x, y }: { id: string; x: number; y: number }): void => {
  const current = document.current.value
  if (current) edit(withNoteAt(current, id, x, y))
}

const onRenameNote = ({ id, title }: { id: string; title: string }): void => {
  const current = document.current.value
  const note = current?.notes?.find((candidate) => candidate.id === id)
  if (current && note) edit(withNote(current, { ...note, title }))
}

const onDeleteNote = ({ id }: { id: string }): void => {
  const current = document.current.value
  if (!current) return
  edit(withoutNote(current, id))
  if (selectedId.value === id) selectedId.value = null
}

/** The frame whose search bar is open, if any. Binding is per-frame because the frame is what
 * decides which area the element lands in — and, from slice 3, which types are offered. */
const bindingInto = ref<string | null>(null)

const onBindRequest = ({ areaId }: { areaId: string }): void => { bindingInto.value = areaId }

/** Place the bound note inside the frame it was requested from, offset so successive picks do not
 * stack on one another. */
const onBindEntity = (entity: EntityDisplayInfo): void => {
  const current = document.current.value
  const areaId = bindingInto.value
  if (!current || !areaId) return
  const rect = current.layout?.areas?.[areaId] ?? [0, 0, 0, 0]
  const alreadyThere = (current.notes ?? []).filter((note) => note.area === areaId).length
  const id = mintId('n')
  const placed = withNoteAt(
    withNote(current, { id, title: entity.name, area: areaId, body: '', destination: 'undecided' }),
    id,
    rect[0] + 40 + (alreadyThere % 5) * 200,
    rect[1] + 60 + Math.floor(alreadyThere / 5) * 90,
  )
  edit(withBinding(placed, id, entity))
  selectedId.value = id
  bindingInto.value = null
}

const onUnbindNote = ({ id }: { id: string }): void => {
  const current = document.current.value
  if (current) edit(withoutBinding(current, id))
}

const onLinkNotes = ({ source, target }: { source: string; target: string }): void => {
  const current = document.current.value
  if (current) edit(withLink(current, mintId('l'), source, target))
}

const selectedNote = computed(() =>
  (document.current.value?.notes ?? []).find((note) => note.id === selectedId.value) ?? null,
)

/** Every refinement is the same shape: take the current document, produce the next, commit it.
 * The aggregate refuses anything these get wrong, and the canvas shows the refusal. */
const refine = (next: (current: Scratchpad) => Scratchpad): void => {
  const current = document.current.value
  if (current) edit(next(current))
}

const undo = (): void => { document.undo(); saver.schedule() }
const redo = (): void => { document.redo(); saver.schedule() }

const onKeydown = (event: KeyboardEvent): void => {
  // Not while a title is being edited: there, Ctrl+Z belongs to the text field.
  if ((event.target as HTMLElement | null)?.isContentEditable) return
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z') return
  event.preventDefault()
  if (event.shiftKey) redo()
  else undo()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

const noteCount = computed(() => document.current.value?.notes?.length ?? 0)
const status = computed(() => {
  if (saver.saveError.value) return saver.saveError.value
  if (saver.saving.value) return 'Saving…'
  return document.dirty.value ? 'Unsaved changes' : 'Saved'
})
</script>

<template>
  <section class="page">
    <header class="bar">
      <div>
        <h1
          class="title"
          data-testid="scratchpad-name"
        >
          {{ document.current.value?.name ?? '…' }}
        </h1>
        <p class="sub">
          <span class="mono">{{ artifactId }}</span>
          <span class="dot">·</span>{{ noteCount }} note{{ noteCount === 1 ? '' : 's' }}
          <span class="dot">·</span><span class="mono">{{ document.current.value?.group }}</span>
        </p>
      </div>
      <div class="actions">
        <button
          type="button"
          :disabled="!document.canUndo.value"
          data-testid="undo"
          @click="undo"
        >
          Undo
        </button>
        <button
          type="button"
          :disabled="!document.canRedo.value"
          data-testid="redo"
          @click="redo"
        >
          Redo
        </button>
        <span
          class="state"
          :class="{ err: !!saver.saveError.value }"
          data-testid="save-state"
        >{{ status }}</span>
      </div>
    </header>

    <p class="hint">
      Double-click the canvas to add a note. Drag a note's right-hand handle onto another to link
      them. Nothing needs a type — that comes later, if it comes at all.
    </p>

    <div class="canvas-frame">
      <ScratchpadCanvas
        v-if="document.current.value"
        :scratchpad="document.current.value"
        :selected-id="selectedId"
        @create-note="onCreateNote"
        @move-note="onMoveNote"
        @rename-note="onRenameNote"
        @delete-note="onDeleteNote"
        @link-notes="onLinkNotes"
        @select="selectedId = $event.id"
        @bind-request="onBindRequest"
        @unbind-note="onUnbindNote"
      />
      <ScratchpadNotePanel
        :note="selectedNote"
        :links="document.current.value?.links ?? []"
        @type-note="refine((c) => withType(c, $event.id, $event.elementType))"
        @untype-note="refine((c) => withoutBinding(withoutType(c, $event.id), $event.id))"
        @forget-note="refine((c) => withoutRealization(c, $event.id))"
        @reverse-link="refine((c) => withReversedLink(c, $event.id))"
        @type-link="refine((c) => withLinkType(c, $event.id, $event.connectionType))"
      />
      <!-- Fixed scale, deliberately: inside the transformed layer the field would shrink with the
           zoom, and this is the one place on the canvas that has to be readable while typing. -->
      <div
        v-if="bindingInto"
        class="bind-panel"
        data-testid="bind-panel"
      >
        <header>
          <span>Add an element that already exists</span>
          <button
            type="button"
            data-testid="bind-cancel"
            @click="bindingInto = null"
          >
            ×
          </button>
        </header>
        <EntityPickerInput
          placeholder="Search the model by name or id…"
          widenable-to="none"
          close-on-select
          @select="onBindEntity"
        />
      </div>
      <p
        v-else-if="loadQuery.error.value"
        class="err"
      >
        This scratchpad could not be loaded.
      </p>
      <p
        v-else
        class="state"
      >
        Loading…
      </p>
    </div>
  </section>
</template>

<style scoped>
.page { max-width: 100%; }
.bar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.title { font-size: 20px; margin: 0 0 2px; }
.sub { margin: 0; font-size: 12px; color: #6b7280; }
.mono { font-family: ui-monospace, monospace; }
.dot { margin: 0 6px; color: #d1d5db; }
.actions { display: flex; align-items: center; gap: 8px; }
.actions button {
  padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff;
  font-size: 13px; cursor: pointer; color: #374151;
}
.actions button:disabled { opacity: .45; cursor: default; }
.actions button:not(:disabled):hover { background: #f9fafb; }
.state { font-size: 12px; color: #6b7280; min-width: 96px; text-align: right; }
.state.err, .err { color: #dc2626; }
.hint { margin: 10px 0; font-size: 12.5px; color: #6b7280; }
.canvas-frame { position: relative; }
.bind-panel {
  position: absolute; top: 14px; right: 14px; width: 380px; z-index: 5;
  background: #fff; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px;
  box-shadow: 0 6px 20px rgba(0,0,0,.10);
}
.bind-panel header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; color: #6b7280; margin-bottom: 8px;
}
.bind-panel header button {
  border: none; background: none; font-size: 16px; line-height: 1; cursor: pointer; color: #9ca3af;
}
.canvas-frame {
  border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;
  height: clamp(420px, 74vh, 940px); background: #fafafa;
}
</style>
