<script setup lang="ts">
/**
 * *Lay out automatically…* on a diagram whose picture is drawn by hand (`manual-layout`, or `written_by_hand`
 * on the read): the picture it would have, generated from what it draws, beside the one it has, and a plain
 * word that the hand-written body is replaced, with what only the hand-drawn picture has. Confirming is the
 * diagram's own replacement with `manual_layout: false` — the save the canvas makes, no write of its own —
 * after which the diagram is arranged on its canvas like any other.
 *
 * The preview is the composition preview every diagram editor reads (`previewDiagram`), from the
 * membership the diagram states.
 */
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { Cause, Effect, Exit, Option } from 'effect'
import { type DiagramDetail, NetworkError } from '../../domain'
import { membershipOf } from '../../domain/layout/diagramMembership'
import type { DiagramComposition } from '../../ports/diagramWriteBodies'
import { modelServiceKey } from '../keys'
import DiagramHandDrawnDetails from './DiagramHandDrawnDetails.vue'

const props = defineProps<{ detail: DiagramDetail }>()
const emit = defineEmits<{ close: []; 'laid-out': [] }>()
const svc = inject(modelServiceKey)!

/** What the diagram states it draws, as the write and the preview take it. */
const composition = computed((): DiagramComposition | null => {
  const stated = membershipOf(props.detail)
  return stated && {
    ...stated, entity_ids: [...stated.entity_ids], connection_ids: [...stated.connection_ids],
    ...(stated.diagram_entities ? { diagram_entities: { ...stated.diagram_entities } } : {}),
  }
})

const generated = ref<string | null>(null)
const failed = ref('')
const writing = ref(false)
/** The picture the diagram has now, as an image of its own: the page's own SVG is never mounted twice. */
const currentUrl = ref<string | null>(null)
const dialog = ref<HTMLElement | null>(null)

const readCurrent = async () => {
  const exit = await Effect.runPromiseExit(svc.getDiagramSvg(props.detail.artifact_id))
  if (Exit.isSuccess(exit)) currentUrl.value = URL.createObjectURL(new Blob([exit.value], { type: 'image/svg+xml' }))
}

onMounted(async () => {
  dialog.value?.focus()
  void readCurrent()
  if (!composition.value) return
  const exit = await Effect.runPromiseExit(svc.previewDiagram(composition.value))
  Exit.match(exit, {
    onSuccess: (preview) => {
      generated.value = preview.image
      if (!preview.image) failed.value = preview.warnings.join(' ') || 'The generated picture could not be drawn.'
    },
    onFailure: (cause) => { failed.value = String(cause) },
  })
})
onBeforeUnmount(() => { if (currentUrl.value) URL.revokeObjectURL(currentUrl.value) })

/**
 * The write carries the revision this page read: a body saved since — from its editor, or by another
 * session — would be replaced unseen, so the server refuses it (409) and the reader is told to look first.
 */
const STALE = 'The diagram changed since this page read it, so laying it out now would replace a body you '
  + 'have not seen. Reload the page to see it, then lay it out.'

const confirm = async () => {
  if (!composition.value) return
  writing.value = true
  failed.value = ''
  const exit = await Effect.runPromiseExit(svc.editDiagram(props.detail.artifact_id, {
    ...composition.value, base_revision: props.detail.revision, manual_layout: false, dry_run: false,
  }))
  writing.value = false
  Exit.match(exit, {
    onSuccess: (result) => {
      if (result.wrote) emit('laid-out')
      else failed.value = result.warnings.join(' ') || 'The diagram was not written.'
    },
    onFailure: (cause) => {
      const failure = Cause.failureOption(cause)
      const conflict = Option.isSome(failure) && failure.value instanceof NetworkError && failure.value.status === 409
      failed.value = conflict ? STALE : String(cause)
    },
  })
}
</script>

<template>
  <div
    class="auto-back"
    @click.self="emit('close')"
  >
    <div
      ref="dialog"
      class="auto"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auto-layout-title"
      data-testid="auto-layout-dialog"
      @keydown.esc.stop="emit('close')"
    >
      <h3 id="auto-layout-title">
        Lay out {{ detail.name }} automatically?
      </h3>
      <p class="auto__lead">
        This diagram's picture is drawn by hand. Laid out automatically, the picture is generated from what
        the diagram draws, and you arrange it and change what it draws on the canvas from there.
      </p>
      <div
        v-if="detail.hand_drawn"
        class="auto__lead"
        data-testid="auto-layout-why"
      >
        <p>The generated picture does not keep what only the hand-drawn one has.</p>
        <DiagramHandDrawnDetails :hand-drawn="detail.hand_drawn" />
      </div>
      <div class="auto__pair">
        <figure>
          <figcaption>Now, drawn by hand</figcaption>
          <img
            v-if="currentUrl"
            :src="currentUrl"
            alt="The diagram as it is drawn now"
          >
          <p v-else>
            Drawing…
          </p>
        </figure>
        <figure>
          <figcaption>Laid out automatically</figcaption>
          <img
            v-if="generated"
            :src="generated"
            alt="The diagram laid out automatically"
            data-testid="auto-layout-preview"
          >
          <p v-else-if="!failed">
            Drawing…
          </p>
        </figure>
      </div>
      <p
        class="auto__warn"
        role="note"
      >
        The hand-written body is replaced by the generated one. The version it replaces stays in the
        diagram's history, from which it can be restored.
      </p>
      <p
        v-if="failed"
        class="auto__error"
        role="alert"
      >
        {{ failed }}
      </p>
      <div class="auto__actions">
        <button
          type="button"
          class="btn"
          @click="emit('close')"
        >
          Keep it as it is
        </button>
        <button
          type="button"
          class="btn btn--primary"
          data-testid="auto-layout-confirm"
          :disabled="writing || !generated"
          @click="confirm"
        >
          {{ writing ? 'Laying out…' : 'Lay out automatically' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auto-back {
  position: fixed; inset: 0; z-index: 110; display: grid; place-items: center;
  background: var(--overlay); padding: 16px;
}
.auto {
  box-sizing: border-box; width: min(1100px, 100%); max-height: calc(100vh - 32px); overflow-y: auto;
  background: var(--surface); color: var(--text); border: 1px solid var(--border-strong);
  border-radius: 10px; box-shadow: var(--shadow); padding: 16px 18px; font-size: 13px;
}
.auto:focus { outline: none; }
.auto h3 { margin: 0 0 6px; font-size: 15px; }
.auto__lead { margin: 0 0 12px; color: var(--muted); }
.auto__pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
figure {
  margin: 0; display: grid; gap: 6px; align-content: start; padding: 8px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--paper);
}
figcaption {
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
}
figure img { display: block; width: 100%; height: auto; max-height: 55vh; object-fit: contain; }
figure p { margin: 0; color: var(--on-paper); }
.auto__warn {
  margin: 12px 0 0; padding: 8px 10px; border-radius: 6px; background: var(--warn-soft);
  border: 1px solid var(--warn-border); color: var(--warn-text);
}
.auto__error {
  margin: 8px 0 0; padding: 6px 8px; border-radius: 5px; background: var(--danger-soft);
  color: var(--danger-strong); border: 1px solid var(--danger-border);
}
.auto__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.btn {
  padding: 5px 14px; font: inherit; font-weight: 500; color: var(--text-2); cursor: pointer;
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 6px;
}
.btn--primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.btn:disabled { opacity: .5; cursor: default; }
</style>
