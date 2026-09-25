<script setup lang="ts">
/**
 * The icons this diagram holds for itself, and the way to move one into the library.
 *
 * Offered here rather than in the editor, because sharing rewrites the saved diagram and an editor
 * holding unsaved changes would then be editing a diagram that has moved underneath it. Once shared,
 * the diagram names the library icon and its own copy is gone; a picture the library already holds is
 * named rather than added twice.
 */
import { computed, inject, ref } from 'vue'
import { Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { WriteResult } from '../../domain/schemas/write-results'
import type { RepoError } from '../../ports/repositoryErrors'
import { useMutation } from '../composables/useMutation'
import { LOCAL_ICONS_KEY } from '../lib/diagramIcons'
import { statementsIn } from '../lib/diagramStatements'
import { rememberAttribution, rememberedAttribution } from '../lib/iconFiles'

const props = defineProps<{ diagramId: string; diagramEntities: Record<string, unknown> }>()
const emit = defineEmits<{ shared: [] }>()

const svc = inject(modelServiceKey)!
/** The diagram's own icons as stored: each under its key, with its name and its normalised picture. */
const own = computed(() =>
  Object.entries(statementsIn(props.diagramEntities, LOCAL_ICONS_KEY)).flatMap(([key, entry]) => {
    const stored = entry as { name?: unknown; 'png-base64'?: unknown }
    if (typeof stored['png-base64'] !== 'string') return []
    const name = typeof stored.name === 'string' ? stored.name : key
    return [{ key, name, picture: `data:image/png;base64,${stored['png-base64']}` }]
  }))

const sharing = ref<string | null>(null)
const attribution = ref(rememberedAttribution())
const share = useMutation<WriteResult, RepoError>()
const refusal = ref<string | null>(null)
const message = computed(() => share.errorMessage.value ?? refusal.value)

const submit = async (key: string): Promise<void> => {
  refusal.value = null
  const exit = await share.run(svc.shareIcon(props.diagramId, key, { attribution: attribution.value, dry_run: false }))
  if (Exit.isFailure(exit)) return
  if (!exit.value.wrote) {
    refusal.value = (exit.value.verification?.issues ?? []).map((issue) => issue.message).join('; ') || 'Refused'
    return
  }
  rememberAttribution(attribution.value)
  sharing.value = null
  emit('shared')
}
</script>

<template>
  <section
    v-if="own.length"
    class="own-icons"
    aria-label="Icons this diagram holds for itself"
  >
    <h3>Icons of this diagram</h3>
    <ul>
      <li
        v-for="icon in own"
        :key="icon.key"
      >
        <img
          :src="icon.picture"
          alt=""
          width="24"
          height="24"
        >
        <span class="name">{{ icon.name }}</span>
        <button
          v-if="sharing !== icon.key"
          @click="sharing = icon.key"
        >
          Add to the library…
        </button>
        <form
          v-else
          class="share"
          @submit.prevent="submit(icon.key)"
        >
          <input
            v-model="attribution"
            required
            placeholder="Whose mark it is, and on what terms it is used"
            aria-label="Attribution"
          >
          <button
            type="submit"
            :disabled="share.running.value"
          >
            Add
          </button>
          <button
            type="button"
            @click="sharing = null"
          >
            Cancel
          </button>
        </form>
      </li>
    </ul>
    <p
      v-if="message"
      class="message"
      role="alert"
    >
      {{ message }}
    </p>
  </section>
</template>

<style scoped>
.own-icons { padding: 10px 12px; border-top: 1px solid #f3f4f6; font-size: 12px; }
.own-icons h3 {
  margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #6b7280;
}
ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
li img { object-fit: contain; }
.name { flex: 1; min-width: 0; color: #1f2937; }
button {
  padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px; background: #fff; cursor: pointer; font-size: 12px;
}
.share { display: flex; gap: 6px; flex: 1 0 100%; }
.share input { flex: 1; padding: 3px 7px; border: 1px solid #e5e7eb; border-radius: 5px; }
.message { margin: 6px 0 0; color: #dc2626; }
</style>
