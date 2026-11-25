<script setup lang="ts">
/**
 * Deleting an element from the model asks first (sketch 03·6): the question in the page's words, the
 * relations that go with it, that it is undoable until Save, and — where the canvas can — taking it
 * off this diagram only, instead. The model's own rule decides what goes: an element's relations from
 * it are deleted with it, and a relation into it from elsewhere keeps Save from deleting it, so both
 * are named. Cancel holds the focus, so Enter on arrival deletes nothing.
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { ConnectionRecord } from '../../domain/schemas/connections'
import { stableEntityId } from '../../domain/artifactId'
import { connectionTypeLabel } from '../lib/connectionTypeGuidance'
import type { CanvasWords } from './canvasWords'

const props = defineProps<{ name: string; entityId: string; words: CanvasWords }>()
const emit = defineEmits<{ confirm: []; remove: []; cancel: [] }>()
const svc = inject(modelServiceKey)!

/** The element's relations in the model; null while they are read or when they could not be. */
const relations = ref<readonly ConnectionRecord[] | null>(null)
onMounted(async () => {
  const exit = await Effect.runPromiseExit(svc.getConnections(props.entityId, 'any'))
  relations.value = Exit.isSuccess(exit) ? exit.value : null
})
const own = computed(() => stableEntityId(props.entityId))
const going = computed(() => relations.value?.filter((one) => stableEntityId(one.source) === own.value) ?? [])
const holding = computed(() => relations.value?.filter((one) => stableEntityId(one.source) !== own.value) ?? [])
const sentence = (one: ConnectionRecord) =>
  `${one.source_name} ${connectionTypeLabel(one.conn_type)} ${one.target_name}`
</script>

<template>
  <div class="cp-form">
    <h3 class="cp-title">
      {{ words.deleteQuestion(name) }}
    </h3>
    <template v-if="relations">
      <p
        class="cp-note"
        data-testid="delete-relations-going"
      >
        {{ going.length ? 'Its relations go with it:' : 'It has no relations of its own to take with it.' }}
      </p>
      <ul
        v-if="going.length"
        class="cp-list"
      >
        <li
          v-for="one in going"
          :key="one.artifact_id"
        >
          {{ sentence(one) }}
        </li>
      </ul>
      <template v-if="holding.length">
        <p
          class="cp-note"
          data-testid="delete-relations-holding"
        >
          Save cannot delete it while these relations point at it; delete them first:
        </p>
        <ul class="cp-list">
          <li
            v-for="one in holding"
            :key="one.artifact_id"
          >
            {{ sentence(one) }}
          </li>
        </ul>
      </template>
    </template>
    <p class="cp-note">
      It joins this edit session; until Save, Undo brings it back.
    </p>
    <div class="cp-row-end">
      <button
        type="button"
        class="cp-btn"
        data-autofocus
        @click="emit('cancel')"
      >
        Cancel
      </button>
      <button
        v-if="words.removeEntry"
        type="button"
        class="cp-btn"
        @click="emit('remove')"
      >
        {{ words.removeEntry }} instead
      </button>
      <button
        type="button"
        class="cp-btn cp-btn--danger"
        @click="emit('confirm')"
      >
        {{ words.deleteConfirm }}
      </button>
    </div>
  </div>
</template>
