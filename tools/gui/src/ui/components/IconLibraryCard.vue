<script setup lang="ts">
/**
 * One icon of the library, and what can be done with it here.
 *
 * An enterprise icon is shown and not edited: this repository reads it and does not own it. Of this
 * repository's own, the name, attribution, what it is for, tags and default style are editable and the
 * picture is not — a new version is another icon, and *Replace…* moves every diagram to it, after
 * listing them. *Delete* is refused while anything shows the icon, and the refusal says what does.
 */
import { computed, inject, ref } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { IconStyle, IconSummary } from '../../domain/schemas/icons'
import type { WriteResult } from '../../domain/schemas/write-results'
import type { RepoError } from '../../ports/repositoryErrors'
import { useMutation } from '../composables/useMutation'
import { csvToList } from '../lib/commaList'

const props = defineProps<{ icon: IconSummary; others: readonly IconSummary[] }>()
const emit = defineEmits<{ changed: [] }>()

const svc = inject(modelServiceKey)!
const mode = ref<'view' | 'edit' | 'replace'>('view')
const write = useMutation<WriteResult | void, RepoError>()
const busy = write.running
const refusal = ref<string | null>(null)
const message = computed(() => write.errorMessage.value ?? refusal.value)

const form = ref({
  name: props.icon.name, attribution: props.icon.attribution, appliesTo: props.icon.applies_to.join(', '),
  tags: props.icon.tags.join(', '), defaultStyle: props.icon.default_style as IconStyle,
})

/** Run one write; a refusal it answers with — rather than fails with — is said on the card too. */
const run = async (effect: Effect.Effect<WriteResult | void, RepoError>, done: () => void): Promise<void> => {
  refusal.value = null
  const exit = await write.run(effect)
  if (Exit.isFailure(exit)) return
  const result = exit.value
  const refused = result ? (result.verification?.issues ?? []).filter((issue) => issue.severity === 'error') : []
  if (result && !result.wrote && refused.length) {
    refusal.value = refused.map((issue) => issue.message).join('; ')
    return
  }
  done()
}

const saveEdit = (): Promise<void> => run(svc.editIcon(props.icon.artifact_id, {
  name: form.value.name, attribution: form.value.attribution, applies_to: csvToList(form.value.appliesTo),
  tags: csvToList(form.value.tags), default_style: form.value.defaultStyle, dry_run: false,
}), () => { mode.value = 'view'; emit('changed') })

const setStatus = (status: 'active' | 'retired'): Promise<void> =>
  run(svc.editIcon(props.icon.artifact_id, { status, dry_run: false }), () => emit('changed'))

const replacement = ref('')
const plan = ref<readonly string[] | null>(null)
const planReplace = (): Promise<void> => run(
  svc.replaceIcon(props.icon.artifact_id, { replacement_id: replacement.value, dry_run: true }).pipe(
    Effect.tap((result) => Effect.sync(() => { plan.value = result.warnings })),
  ),
  () => undefined,
)
const confirmReplace = (): Promise<void> => run(
  svc.replaceIcon(props.icon.artifact_id, { replacement_id: replacement.value, dry_run: false }),
  () => emit('changed'),
)
const remove = (): Promise<void> => run(svc.deleteIcon(props.icon.artifact_id), () => emit('changed'))
</script>

<template>
  <article
    class="card"
    :class="{ 'card--retired': icon.status === 'retired' }"
  >
    <div class="head">
      <img
        :src="svc.iconImageUrl(icon.artifact_id)"
        alt=""
        width="40"
        height="40"
      >
      <div class="text">
        <h3>{{ icon.name }}</h3>
        <p class="attribution">
          {{ icon.attribution }}
        </p>
        <p class="meta">
          For {{ icon.applies_to.length ? icon.applies_to.join(', ') : 'any element' }} · {{ icon.default_style }}
          <span v-if="icon.tags.length"> · {{ icon.tags.join(', ') }}</span>
        </p>
      </div>
      <span
        v-if="icon.is_global"
        class="badge"
      >Enterprise</span>
      <span
        v-else-if="icon.status === 'retired'"
        class="badge badge--retired"
      >Retired</span>
    </div>

    <div
      v-if="!icon.is_global && mode === 'view'"
      class="actions"
    >
      <button @click="mode = 'edit'">
        Edit
      </button>
      <button
        :disabled="busy"
        @click="setStatus(icon.status === 'retired' ? 'active' : 'retired')"
      >
        {{ icon.status === 'retired' ? 'Reinstate' : 'Retire' }}
      </button>
      <button @click="mode = 'replace'; plan = null">
        Replace…
      </button>
      <button
        class="danger"
        :disabled="busy"
        @click="remove"
      >
        Delete
      </button>
    </div>

    <form
      v-if="mode === 'edit'"
      class="form"
      @submit.prevent="saveEdit"
    >
      <label>Name <input
        v-model="form.name"
        required
      ></label>
      <label>Attribution <input
        v-model="form.attribution"
        required
      ></label>
      <label>For <input
        v-model="form.appliesTo"
        placeholder="empty for any element"
      ></label>
      <label>Tags <input v-model="form.tags"></label>
      <label>Default style <select v-model="form.defaultStyle">
        <option value="badge">Badge</option>
        <option value="figure">Figure</option>
      </select></label>
      <div class="actions">
        <button
          type="submit"
          class="primary"
          :disabled="busy"
        >
          Save
        </button>
        <button
          type="button"
          @click="mode = 'view'"
        >
          Cancel
        </button>
      </div>
    </form>

    <div
      v-if="mode === 'replace'"
      class="form"
    >
      <label>Replace with
        <select
          v-model="replacement"
          @change="plan = null"
        >
          <option
            v-for="other in others"
            :key="other.artifact_id"
            :value="other.artifact_id"
          >{{ other.name }}</option>
        </select>
      </label>
      <ul
        v-if="plan"
        class="plan"
      >
        <li v-if="!plan.length">
          No diagram shows it; it is deleted.
        </li>
        <li
          v-for="line in plan"
          :key="line"
        >
          {{ line }}
        </li>
      </ul>
      <div class="actions">
        <button
          v-if="!plan"
          class="primary"
          :disabled="busy || !replacement"
          @click="planReplace"
        >
          Show what moves
        </button>
        <button
          v-else
          class="primary"
          :disabled="busy"
          @click="confirmReplace"
        >
          Replace and delete this icon
        </button>
        <button @click="mode = 'view'">
          Cancel
        </button>
      </div>
    </div>

    <p
      v-if="message"
      class="message"
      role="alert"
    >
      {{ message }}
    </p>
  </article>
</template>

<style scoped>
.card {
  display: flex; flex-direction: column; gap: 8px; padding: 10px;
  border: 1px solid #e5e7eb; border-radius: 8px; background: #fff;
}
.card--retired { opacity: .7; }
.head { display: flex; gap: 10px; align-items: flex-start; }
.head img { object-fit: contain; flex-shrink: 0; }
.text { flex: 1; min-width: 0; }
.text h3 { margin: 0; font-size: 14px; color: #1f2937; }
.attribution, .meta { margin: 2px 0 0; font-size: 11px; color: #6b7280; overflow-wrap: anywhere; }
.badge {
  font-size: 10px; font-weight: 700; color: #1d4ed8;
  background: #dbeafe; border-radius: 999px; padding: 2px 7px;
}
.badge--retired { color: #92400e; background: #fef3c7; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; }
.actions button {
  padding: 3px 9px; font-size: 12px; border-radius: 5px;
  border: 1px solid #d1d5db; background: #fff; cursor: pointer;
}
.actions .primary { background: #2563eb; border-color: #2563eb; color: #fff; }
.actions .danger { color: #dc2626; border-color: #fecaca; }
.actions button:disabled { opacity: .5; cursor: not-allowed; }
.form { display: flex; flex-direction: column; gap: 6px; font-size: 12px; }
.form label { display: flex; flex-direction: column; gap: 2px; font-weight: 600; color: #374151; }
.form input, .form select { font-weight: 400; padding: 4px 7px; border: 1px solid #e5e7eb; border-radius: 5px; }
.plan { margin: 0; padding-left: 18px; color: #374151; }
.message { margin: 0; font-size: 12px; color: #dc2626; }
</style>
