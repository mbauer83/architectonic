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
import { useScratchpadLift } from '../composables/useScratchpadLift'
import { fetchRelationNotations, type RelationNotation } from '../lib/relationNotations'
import ScratchpadCanvasMenu from '../components/ScratchpadCanvasMenu.vue'
import ScratchpadHeader from '../components/ScratchpadHeader.vue'
import ScratchpadLiftDialog from '../components/ScratchpadLiftDialog.vue'
import ScratchpadNotePanel from '../components/ScratchpadNotePanel.vue'
import { useScratchpadDocument } from '../composables/useScratchpadDocument'
import {
  areaAtPoint,
  toReplacePayload,
  withBinding,
  withBody,
  withDocumentType,
  withDomain,
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
/** One selection, not two. The note panel edits it when exactly one note is in it, which is what
 * a person means by "the selected note"; a lift acts on all of it. */
const selected = ref<string[]>([])
/** A link may be selected instead, so it can be refined without going through a note. */
const selectedLinkId = ref<string | null>(null)

/** The frame being worked in. Focus fits the view to it and fades the rest back; nothing leaves
 * the document, because the links that cross frames are the content worth having. */
const focusedAreaId = ref<string | null>(null)

/** One request per canvas, not one per link: how the ontology says each relation is drawn. */
const notations = ref<ReadonlyMap<string, RelationNotation>>(new Map())
void fetchRelationNotations().then((found) => { notations.value = found })

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
  const blank = { id, title: 'New note', area: areaAtPoint(current, x, y), body: '', destination: 'undecided' } as const
  edit(withNoteAt(withNote(current, blank), id, x, y))
  selected.value = [id]
  menu.value = null
  // Focus the title so a new note opens ready to be written, which is the whole gesture.
  requestAnimationFrame(() => editTitle({ id }))
}

/** Put the caret in a note's title. Reached by a click, by `Enter`/`F2` on a focused note, and by
 * creating one — all three mean the same thing, so they go through one function. */
const editTitle = ({ id }: { id: string }): void => {
  const field = window.document.querySelector<HTMLElement>(`[data-note-title="${id}"]`)
  field?.focus()
  if (field) window.getSelection()?.selectAllChildren(field)
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
  selected.value = selected.value.filter((candidate) => candidate !== id)
}

/** Where the canvas menu was opened, in both coordinate systems: the canvas point decides where
 * whatever is added lands, the viewport point decides where the menu is drawn. */
const menu = ref<{ at: { x: number; y: number }; screen: { x: number; y: number } } | null>(null)

const onMenuRequest = (payload: NonNullable<typeof menu.value>): void => { menu.value = payload }

/** The frame under the menu, and what it permits. A click outside every frame is `unfiled`, which
 * is a legitimate place to be and narrows nothing. */
const menuArea = computed(() => {
  const current = document.current.value
  if (!current || !menu.value) return null
  const areaId = areaAtPoint(current, menu.value.at.x, menu.value.at.y)
  return (current.areas ?? []).find((area) => area.id === areaId) ?? null
})

/** The bound note lands exactly where the menu was opened. That is the whole reason the gesture
 * moved onto the canvas: area membership is spatial, so the point of insertion is the decision. */
const onBindEntity = (entity: EntityDisplayInfo): void => {
  const current = document.current.value
  const at = menu.value?.at
  if (!current || !at) return
  const id = mintId('n')
  const placed = withNoteAt(
    withNote(current, {
      id, title: entity.name, area: areaAtPoint(current, at.x, at.y), body: '', destination: 'undecided',
    }),
    id,
    at.x,
    at.y,
  )
  edit(withBinding(placed, id, entity))
  selected.value = [id]
  menu.value = null
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
  selected.value.length === 1
    ? (document.current.value?.notes ?? []).find((note) => note.id === selected.value[0]) ?? null
    : null,
)

const selectedLink = computed(() =>
  (document.current.value?.links ?? []).find((link) => link.id === selectedLinkId.value) ?? null,
)

const onSelect = ({ id, additive }: { id: string | null; additive: boolean }): void => {
  menu.value = null
  selectedLinkId.value = null
  if (id === null) { selected.value = [] ; return }
  if (!additive) { selected.value = [id] ; return }
  selected.value = selected.value.includes(id)
    ? selected.value.filter((candidate) => candidate !== id)
    : [...selected.value, id]
}

/** Every refinement is the same shape: take the current document, produce the next, commit it.
 * The aggregate refuses anything these get wrong, and the canvas shows the refusal. */
const refine = (next: (current: Scratchpad) => Scratchpad): void => {
  const current = document.current.value
  if (current) edit(next(current))
}

/** A committed lift rewrites the notes it realized, so the canvas reloads rather than guessing.
 * Reloading also drops the undo history, which is correct: what a lift created is not undoable
 * from here, and offering an undo that only rolls back the *notes* would be a lie. */
const lift = useScratchpadLift(
  svc, artifactId, () => document.current.value, () => { load() }, () => saver.flush(),
)

const onLiftRequest = (): void => {
  menu.value = null
  void lift.preflight(selected.value)
}

const undo = (): void => { document.undo(); saver.schedule() }
const redo = (): void => { document.redo(); saver.schedule() }

const onKeydown = (event: KeyboardEvent): void => {
  // Not while a title is being edited: there, Ctrl+Z belongs to the text field.
  if ((event.target as HTMLElement | null)?.isContentEditable) return
  // Escape leaves focus before it clears a selection: the mode is the more surprising state to be
  // stuck in, and a person pressing Escape means "get me out of this" either way.
  if (event.key === 'Escape' && focusedAreaId.value) {
    focusedAreaId.value = null
    return
  }
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
    <ScratchpadHeader
      :name="document.current.value?.name ?? '…'"
      :artifact-id="artifactId"
      :group="document.current.value?.group ?? ''"
      :note-count="noteCount"
      :can-undo="document.canUndo.value"
      :can-redo="document.canRedo.value"
      :focused="!!focusedAreaId"
      :status="status"
      :failed="!!saver.saveError.value"
      @undo="undo"
      @redo="redo"
      @leave-focus="focusedAreaId = null"
    />

    <p class="hint">
      Double-click the canvas to add a note, or right-click to add one the model already has.
      Drag a note's right-hand handle onto another to link them. Nothing needs a type — that comes
      later, if it comes at all.
    </p>

    <div class="canvas-frame">
      <ScratchpadCanvas
        v-if="document.current.value"
        :scratchpad="document.current.value"
        :selected-ids="selected"
        :selected-link-id="selectedLinkId"
        :focused-area-id="focusedAreaId"
        :notations="notations"
        @create-note="onCreateNote"
        @move-note="onMoveNote"
        @rename-note="onRenameNote"
        @delete-note="onDeleteNote"
        @link-notes="onLinkNotes"
        @select="onSelect"
        @select-link="selectedLinkId = $event.id; selected = []"
        @edit-title="editTitle"
        @menu-request="onMenuRequest"
        @unbind-note="onUnbindNote"
      />
      <ScratchpadNotePanel
        :note="selectedNote"
        :selected-link="selectedLink"
        :notes="document.current.value?.notes ?? []"
        :links="document.current.value?.links ?? []"
        @type-note="refine((c) => withType(c, $event.id, $event.elementType))"
        @domain-note="refine((c) => withDomain(c, $event.id, $event.domain))"
        @body-note="refine((c) => withBody(c, $event.id, $event.body))"
        @document-note="refine((c) => withDocumentType(c, $event.id, $event.documentType))"
        @untype-note="refine((c) => withoutBinding(withoutType(c, $event.id), $event.id))"
        @forget-note="refine((c) => withoutRealization(c, $event.id))"
        @reverse-link="refine((c) => withReversedLink(c, $event.id))"
        @type-link="refine((c) => withLinkType(c, $event.id, $event.connectionType))"
      />
      <ScratchpadCanvasMenu
        :at="menu?.screen ?? null"
        :area-label="menuArea?.label ?? ''"
        :permitted-types="menuArea?.['permitted-element-types'] ?? []"
        :selection-size="selected.length"
        :focused="focusedAreaId === menuArea?.id"
        :can-focus="!!menuArea"
        @focus-area="focusedAreaId = focusedAreaId === menuArea?.id ? null : (menuArea?.id ?? null);
                     menu = null"
        @new-note="menu && onCreateNote(menu.at)"
        @add-existing="onBindEntity"
        @lift="onLiftRequest"
        @close="menu = null"
      />
      <ScratchpadLiftDialog
        :open="lift.open.value"
        :plan="lift.plan.value"
        :projects="lift.projects.value"
        :frames="lift.frames.value"
        :targets="lift.targets.value"
        :draw="lift.draw.value"
        :busy="lift.busy.value"
        :error="lift.error.value"
        :selection-size="lift.selectionSize.value"
        @set-target="lift.setTarget($event.frame, $event.slug)"
        @update:draw="lift.draw.value = $event"
        @lift="lift.lift()"
        @close="lift.close()"
      />
      <p
        v-if="loadQuery.error.value"
        class="err"
      >
        This scratchpad could not be loaded.
      </p>
      <!-- Only while there is nothing to draw. As a bare `v-else` on the error branch this said
           "Loading…" underneath a fully loaded canvas forever, which the media capture refused to
           photograph — correctly, since a shot of a page still claiming to load is a shot of a
           product that looks broken. -->
      <p
        v-else-if="!document.current.value"
        class="state"
      >
        Loading…
      </p>
    </div>
  </section>
</template>

<style scoped>
.page { max-width: 100%; }
.err { color: #dc2626; }
.hint { margin: 10px 0; font-size: 12.5px; color: #6b7280; }
.canvas-frame {
  position: relative;
  border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;
  height: clamp(420px, 74vh, 940px); background: #fafafa;
}
</style>
