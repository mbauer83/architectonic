<script setup lang="ts">
/**
 * Add an icon to this repository's library.
 *
 * The file is checked by a dry run before anything is written, so the author sees what the library
 * would store — or why it will not — first: a removed script element is a note, an oversized picture a
 * refusal. The attribution is kept for the session, so adding a vendor's set asks for it once.
 */
import { inject, ref } from 'vue'
import { Cause, Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { IconStyle } from '../../domain/schemas/icons'
import type { IconUploadForDiagram } from '../lib/diagramIcons'
import { ICON_FILE_TYPES, iconUploadFromFile } from '../lib/iconFiles'
import { formatEffectError } from '../lib/errors'

const emit = defineEmits<{ added: [iconId: string]; cancel: [] }>()

const ATTRIBUTION_KEY = 'arch.icons.lastAttribution'
const remembered = (): string => {
  try { return sessionStorage.getItem(ATTRIBUTION_KEY) ?? '' } catch { return '' }
}

const svc = inject(modelServiceKey)!
const file = ref<IconUploadForDiagram | null>(null)
const name = ref('')
const attribution = ref(remembered())
const appliesTo = ref('')
const tags = ref('')
const defaultStyle = ref<IconStyle>('badge')
const notes = ref<readonly string[]>([])
const refusal = ref<string | null>(null)
const checked = ref(false)
const busy = ref(false)

const listOf = (text: string): string[] => text.split(',').map((item) => item.trim()).filter(Boolean)

const onFile = async (event: Event): Promise<void> => {
  const chosen = (event.target as HTMLInputElement).files?.[0]
  checked.value = false
  if (!chosen) return
  const upload = await iconUploadFromFile(chosen)
  if ('refused' in upload) {
    refusal.value = upload.refused
    file.value = null
    return
  }
  file.value = upload
  name.value = name.value || upload.name
  refusal.value = null
}

const submit = async (dryRun: boolean): Promise<void> => {
  if (!file.value) return
  busy.value = true
  const exit = await Effect.runPromiseExit(svc.createIcon({
    ...file.value, name: name.value, attribution: attribution.value, applies_to: listOf(appliesTo.value),
    tags: listOf(tags.value), default_style: defaultStyle.value, dry_run: dryRun,
  }))
  busy.value = false
  if (Exit.isFailure(exit)) {
    refusal.value = formatEffectError(Cause.squash(exit.cause))
    return
  }
  const result = exit.value
  const errors = (result.verification?.issues ?? []).filter((issue) => issue.severity === 'error')
  notes.value = result.warnings
  const refused = errors.map((issue) => issue.message).join('; ') || 'Refused'
  refusal.value = result.verification?.valid === false ? refused : null
  checked.value = refusal.value === null
  if (!dryRun && result.wrote) {
    try { sessionStorage.setItem(ATTRIBUTION_KEY, attribution.value) } catch { /* a private window keeps none */ }
    emit('added', result.artifact_id)
  }
}
</script>

<template>
  <form
    class="add-form"
    @submit.prevent="submit(!checked)"
  >
    <label class="field">Picture
      <input
        type="file"
        :accept="ICON_FILE_TYPES"
        required
        @change="onFile"
      >
    </label>
    <label class="field">Name <input
      v-model="name"
      required
      @input="checked = false"
    ></label>
    <label class="field">Whose mark it is, and on what terms it is used <input
      v-model="attribution"
      required
      placeholder="Microsoft Azure architecture icons, used under …"
      @input="checked = false"
    ></label>
    <label class="field">For (types or specializations, comma-separated; empty for any element) <input
      v-model="appliesTo"
      placeholder="technology-node, kubernetes-cluster"
      @input="checked = false"
    ></label>
    <label class="field">Tags <input
      v-model="tags"
      placeholder="azure, containers"
    ></label>
    <label class="field">Default style
      <select v-model="defaultStyle">
        <option value="badge">Badge — beside the name</option>
        <option value="figure">Figure — the element itself</option>
      </select>
    </label>
    <ul
      v-if="notes.length"
      class="notes"
    >
      <li
        v-for="note in notes"
        :key="note"
      >
        {{ note }}
      </li>
    </ul>
    <p
      v-if="refusal"
      class="refusal"
      role="alert"
    >
      {{ refusal }}
    </p>
    <div class="actions">
      <button
        type="submit"
        class="primary"
        :disabled="busy || !file"
      >
        {{ checked ? 'Add to the library' : 'Check' }}
      </button>
      <button
        type="button"
        @click="emit('cancel')"
      >
        Cancel
      </button>
    </div>
  </form>
</template>

<style scoped>
.add-form {
  display: flex; flex-direction: column; gap: 8px; padding: 12px;
  border: 1px solid #e5e7eb; border-radius: 8px; background: #fff;
}
.field { display: flex; flex-direction: column; gap: 3px; font-size: 12px; font-weight: 600; color: #374151; }
.field input, .field select {
  font-weight: 400; padding: 5px 8px; border: 1px solid #e5e7eb;
  border-radius: 6px; font-size: 13px;
}
.notes { margin: 0; padding-left: 18px; font-size: 12px; color: #92400e; }
.refusal { margin: 0; font-size: 12px; color: #dc2626; }
.actions { display: flex; gap: 8px; }
.actions button { padding: 5px 12px; border-radius: 6px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; }
.actions .primary { background: #2563eb; border-color: #2563eb; color: #fff; }
.actions button:disabled { opacity: .5; cursor: not-allowed; }
</style>
