<script setup lang="ts">
/**
 * *Edit details…* (sketch 01·10, 03·5): the product's own entity form — its name and status as the
 * entity page's header edits them, and the form card (`EntityEditFormCard`) for the rest — in a modal
 * over the canvas. Its Save does not write: it keeps the edit in the canvas session (`keep`), as a
 * rename and a `model.element.edit`, so the session's Save writes it with the diagram, Undo takes it
 * back and Discard drops it. Preview asks the write path for a dry run, which writes nothing.
 *
 * A host whose session edits something other than the model provides a `DetailsSource`: the form then
 * opens on the element as that holds it, each field that differs from what it stands on is listed with
 * the value there, and the note under the heading is the host's.
 */
import { computed, inject, nextTick, onMounted, provide, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { EntityDetail } from '../../domain'
import { entityEditFormKey, useEntityEditForm } from '../composables/useEntityEditForm'
import type { CanvasCommand, ElementDetailsEdit } from '../../ports/diagramWriteBodies'
import EntityEditFormCard from './EntityEditFormCard.vue'
import { withPendingDetails } from '../../domain/layout/canvasComposition'
import { shownValue, withHeldDetails } from '../../domain/heldDetails'
import { detailsSourceKey, type HeldElement } from './canvasDetails'
import { useOverlayHost } from '../composables/useOverlayHost'

const props = defineProps<{
  artifactId: string
  /** The session's commands: a second edit opens on what the first one kept. */
  pending: readonly CanvasCommand[]
  /** Keeps the commands in the session: answers why they were refused, or null. */
  keep: (commands: readonly CanvasCommand[]) => Promise<string | null>
}>()
const emit = defineEmits<{ close: [] }>()
const svc = inject(modelServiceKey)!
const source = inject(detailsSourceKey, null)
const held = ref<HeldElement | null>(null)
const note = computed(() => source?.note
  ?? 'Kept with this edit session and written when you Save; Undo takes it back.')

const detail = ref<EntityDetail | null>(null)
const failed = ref('')
const nameField = ref<HTMLInputElement | null>(null)
const entityId = computed(() => props.artifactId)

const commandsOf = (body: Record<string, unknown>): CanvasCommand[] => {
  const { name, ...fields } = body
  const renamed = typeof name === 'string' && name.trim() && name !== detail.value?.name
    ? [{ op: 'model.element.rename' as const, artifact_id: props.artifactId, name: name.trim() }] : []
  const stated = Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined))
  return [...renamed, { op: 'model.element.edit', artifact_id: props.artifactId, ...stated as ElementDetailsEdit }]
}
const edit = useEntityEditForm({
  svc, entityId, detail, editFn: ref(svc.editEntity), onSaved: () => emit('close'),
  keep: (body) => props.keep(commandsOf(body)),
})
provide(entityEditFormKey, edit)
// The form's own Cancel ends its edit: the dialog goes with it.
watch(() => edit.editing, (now, was) => { if (was && !now) emit('close') })

onMounted(async () => {
  try {
    const [model, holding] = await Promise.all([
      Effect.runPromise(svc.getEntity(props.artifactId)), source?.read(props.artifactId) ?? Promise.resolve(null),
    ])
    held.value = holding
    detail.value = withPendingDetails(holding ? withHeldDetails(model, holding.fields) : model, props.pending)
    edit.startEdit()
    await nextTick()
    nameField.value?.focus()
  } catch (e) {
    failed.value = String(e)
  }
})
/** Opened over the canvas while it has the screen, where the body would not be painted. */
const overlayHost = useOverlayHost()
</script>

<template>
  <Teleport :to="overlayHost">
    <div
      class="details-back"
      @pointerdown.self="emit('close')"
    >
      <div
        class="details"
        role="dialog"
        aria-modal="true"
        :aria-label="`Edit details: ${detail?.name ?? ''}`"
        @keydown.esc.stop.prevent="emit('close')"
      >
        <header class="details__head">
          <h3>Edit details</h3>
          <p>{{ note }}</p>
        </header>
        <section
          v-if="held?.differs.length"
          class="details__beneath"
          data-testid="details-differs"
        >
          <h4>Differs from {{ held.beneath }}</h4>
          <dl>
            <template
              v-for="one in held.differs"
              :key="one.field"
            >
              <dt>{{ one.field }}</dt>
              <dd>{{ held.beneath }} has <s>{{ shownValue(one.beneath) }}</s></dd>
            </template>
          </dl>
        </section>
        <p
          v-if="failed"
          class="details__error"
          role="alert"
        >
          {{ failed }}
        </p>
        <template v-else-if="detail">
          <div class="details__row">
            <label>
              <span>Name</span>
              <input
                ref="nameField"
                v-model="edit.editName"
              >
            </label>
            <label>
              <span>Status</span>
              <select v-model="edit.editStatus">
                <option value="draft">draft</option>
                <option value="active">active</option>
                <option value="deprecated">deprecated</option>
              </select>
            </label>
          </div>
          <EntityEditFormCard
            v-if="edit.editing"
            :is-global-entity="false"
            save-label="Keep changes"
          />
        </template>
        <p
          v-else
          class="details__loading"
        >
          Reading the element…
        </p>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.details-back {
  position: fixed; inset: 0; z-index: 110; display: grid; place-items: center;
  background: var(--overlay); padding: 16px;
}
.details {
  box-sizing: border-box; width: min(600px, 100%); max-height: calc(100vh - 32px); overflow-y: auto;
  background: var(--surface); color: var(--text); border: 1px solid var(--border-strong);
  border-radius: 10px; box-shadow: var(--shadow); padding: 16px 18px; font-size: 13px;
}
.details__head h3 { margin: 0 0 2px; font-size: 14px; }
.details__head p, .details__loading { margin: 0 0 12px; color: var(--muted); font-size: 12px; }
.details__row { display: grid; grid-template-columns: 1fr 160px; gap: 10px; margin-bottom: 12px; }
.details__row label { display: grid; gap: 4px; }
.details__row span {
  font-size: 12px; font-weight: 600; color: var(--text-2); text-transform: uppercase; letter-spacing: .04em;
}
.details__row input, .details__row select {
  box-sizing: border-box; width: 100%; padding: 6px 8px; font: inherit; color: var(--text);
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 5px;
}
.details__row input:focus, .details__row select:focus {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-ring);
}
.details__beneath {
  margin: 0 0 12px; padding: 6px 8px; border-radius: 5px; background: var(--warn-soft);
  border-left: 3px solid var(--warn-text); font-size: 12px;
}
.details__beneath h4 { margin: 0 0 4px; font-size: 12px; }
.details__beneath dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 10px; margin: 0; }
.details__beneath dt { font-weight: 600; color: var(--text-2); }
.details__beneath dd { margin: 0; color: var(--text-2); overflow-wrap: anywhere; }
.details__beneath s { color: var(--warn-text); }
.details__error {
  padding: 6px 8px; border-radius: 5px; background: var(--danger-soft); color: var(--danger-strong);
  border: 1px solid var(--danger-border);
}
.details :deep(.edit-form.card) { border: none; box-shadow: none; padding: 0; margin: 0; }
</style>
