<script setup lang="ts">
/**
 * The preflight, before a sketch becomes model content.
 *
 * Lift is the one irreversible thing a scratchpad does, so this dialog exists to make sure nobody
 * is surprised by it. It shows the plan the server produced — the same plan the execution runs, not
 * a client's guess at it — grouped by what will happen: created, skipped because it is already in
 * the model, refused, and the links that reach outside the selection.
 *
 * **Refusals block the whole lift**, and the button says so rather than being merely disabled: the
 * write is one transaction, and half a lift is a state nobody asked for.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { LiftItem, ScratchpadLift } from '../../domain/schemas/scratchpads'

const props = defineProps<{
  open: boolean
  plan: ScratchpadLift | null
  /** Model-project slugs already in the repository, offered before a new one is typed. */
  projects: readonly string[]
  target: string
  busy: boolean
  error: string
  selectionSize: number
}>()

const emit = defineEmits<{
  (event: 'update:target', value: string): void
  (event: 'lift'): void
  (event: 'close'): void
}>()

const dialog = ref<HTMLElement | null>(null)

/** A modal is only modal if focus goes into it: opening one behind the page's tab order leaves a
 * keyboard user reading a scrim. Escape closes, which is the other half of the same contract. */
watch(() => props.open, (open) => {
  if (open) void nextTick(() => dialog.value?.focus())
})

const items = computed<readonly LiftItem[]>(() => props.plan?.items ?? [])
const of = (outcome: LiftItem['outcome']) => computed(() => items.value.filter((item) => item.outcome === outcome))

const creates = of('create')
const skipped = of('skip')
const refused = of('refuse')
const warnings = computed(() => items.value.filter((item) => item.warning))
const outside = computed(() => props.plan?.['outside-selection'] ?? [])

const blocked = computed(() => props.plan?.blocks === true)
const committed = computed(() => props.plan?.committed === true)
const newProject = computed(() => !!props.target && !props.projects.includes(props.target))
</script>

<template>
  <div
    v-if="open"
    class="scrim"
    data-testid="lift-dialog"
  >
    <section
      ref="dialog"
      class="dialog"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      aria-label="Lift into the model"
      @keydown.esc.stop="emit('close')"
    >
      <header>
        <h2>Lift {{ selectionSize }} note{{ selectionSize === 1 ? '' : 's' }} into the model</h2>
        <button
          type="button"
          class="close"
          data-testid="lift-close"
          @click="emit('close')"
        >
          ×
        </button>
      </header>

      <p
        v-if="committed"
        class="done"
        data-testid="lift-done"
      >
        Lifted. The notes now carry what they became, and a second lift will skip them.
      </p>

      <template v-else>
        <label class="field">
          <span>Into</span>
          <input
            list="lift-projects"
            data-testid="lift-target"
            placeholder="the root model"
            :value="target"
            @input="emit('update:target', ($event.target as HTMLInputElement).value)"
          >
          <datalist id="lift-projects">
            <option
              v-for="slug in projects"
              :key="slug"
              :value="slug"
            />
          </datalist>
        </label>
        <p class="note">
          <!-- Creating the project here is deliberate: "this thinking has become a project" is the
               normal way a project starts, and leaving to make one would interrupt the moment. -->
          <span v-if="newProject">A new project <code>{{ target }}</code> will be created for it.</span>
          <span v-else-if="!target">Content that belongs to no project goes to the root model.</span>
          <span v-else>An existing project.</span>
        </p>
      </template>

      <p
        v-if="plan?.refusal"
        class="refusal"
        data-testid="lift-refusal"
      >
        {{ plan.refusal }}
      </p>

      <div class="groups">
        <section
          v-if="creates.length"
          data-testid="lift-creates"
        >
          <h3>Will be created ({{ creates.length }})</h3>
          <ul>
            <li
              v-for="item in creates"
              :key="item.id"
            >
              <span class="label">{{ item.label }}</span>
              <code v-if="item['artifact-type']">{{ item['artifact-type'] }}</code>
            </li>
          </ul>
        </section>

        <section
          v-if="refused.length"
          class="bad"
          data-testid="lift-refused"
        >
          <h3>Refused ({{ refused.length }})</h3>
          <ul>
            <li
              v-for="item in refused"
              :key="item.id"
            >
              <span class="label">{{ item.label }}</span>
              <span class="why"><code v-if="item.code">{{ item.code }}</code> {{ item.reason }}</span>
            </li>
          </ul>
        </section>

        <section
          v-if="skipped.length"
          class="muted"
          data-testid="lift-skipped"
        >
          <!-- Skipped, never updated: what a scratchpad put into the model is not the scratchpad's
               to rewrite, so a second lift adds only what is new. -->
          <h3>Already in the model ({{ skipped.length }})</h3>
          <ul>
            <li
              v-for="item in skipped"
              :key="item.id"
            >
              <span class="label">{{ item.label }}</span>
              <code>{{ item['artifact-id'] }}</code>
            </li>
          </ul>
        </section>

        <section
          v-if="warnings.length"
          class="warn"
          data-testid="lift-warnings"
        >
          <h3>Warnings ({{ warnings.length }})</h3>
          <ul>
            <li
              v-for="item in warnings"
              :key="`w-${item.id}`"
            >
              <span class="label">{{ item.label }}</span>
              <span class="why">{{ item.warning }}</span>
            </li>
          </ul>
        </section>

        <section
          v-if="outside.length"
          class="muted"
          data-testid="lift-outside"
        >
          <h3>Links reaching outside the selection ({{ outside.length }})</h3>
          <p class="why">
            These are not realized. Add the note at the other end to the selection, or accept it.
          </p>
          <ul>
            <li
              v-for="stranded in outside"
              :key="stranded['link-id']"
            >
              <span class="label">→ {{ stranded['note-title'] }}</span>
            </li>
          </ul>
        </section>
      </div>

      <p
        v-if="error"
        class="refusal"
        data-testid="lift-error"
      >
        {{ error }}
      </p>

      <footer>
        <span
          v-if="blocked"
          class="why"
        >A refusal stops the whole lift — the write is one transaction.</span>
        <button
          type="button"
          @click="emit('close')"
        >
          {{ committed ? 'Close' : 'Cancel' }}
        </button>
        <button
          v-if="!committed"
          type="button"
          class="primary"
          data-testid="lift-confirm"
          :disabled="blocked || busy || !creates.length"
          @click="emit('lift')"
        >
          {{ busy ? 'Lifting…' : `Lift ${creates.length}` }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed; inset: 0; z-index: 20; background: rgba(15,17,20,.35);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.dialog {
  outline: none;
  background: #fff; border-radius: 10px; width: min(680px, 100%); max-height: 82vh;
  display: flex; flex-direction: column; padding: 16px 18px;
  box-shadow: 0 20px 50px rgba(0,0,0,.24); font-size: 13px;
}
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { font-size: 15px; margin: 0 0 10px; }
h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; margin: 0 0 4px; }
.close { border: none; background: none; font-size: 18px; line-height: 1; cursor: pointer; color: #9ca3af; }
.field { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.field span { color: #6b7280; }
.field input { flex: 1; padding: 5px 8px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; }
.note { margin: 0 0 10px; color: #6b7280; font-size: 11.5px; }
.groups { overflow-y: auto; flex: 1; }
.groups section { margin-bottom: 12px; }
ul { list-style: none; margin: 0; padding: 0; }
li { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; padding: 2px 0; }
.label { flex: 1 1 auto; }
.why { color: #6b7280; font-size: 11.5px; flex: 1 1 100%; }
code { font-size: 11px; color: #4b5563; background: #f3f4f6; padding: 0 4px; border-radius: 3px; }
.bad .label { color: #dc2626; }
.warn .label { color: #d97706; }
.muted .label { color: #6b7280; }
.refusal { color: #dc2626; margin: 4px 0; }
.done { color: #059669; margin: 8px 0; }
footer { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding-top: 10px; }
footer .why { flex: 1 1 auto; }
footer button {
  padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff;
  font-size: 13px; cursor: pointer; color: #374151;
}
footer button.primary { border-color: #2563eb; background: #2563eb; color: #fff; font-weight: 600; }
footer button:disabled { opacity: .45; cursor: default; }
</style>
