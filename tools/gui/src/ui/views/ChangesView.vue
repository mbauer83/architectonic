<script setup lang="ts">
/**
 * What this repository has changed in content it does not own.
 *
 * Editing a promoted artifact records a change against it rather than writing — there is nowhere
 * local to write. Without this page that recording is something that happens to an author and never
 * appears again, which is the difference between a feature and a side effect.
 *
 * Rows name the artifact, never the change file: an author did not author it and has no use for its
 * id. The link goes to the reference, because that is what this repository can open.
 */
import { inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { ChangeSummary } from '../../domain/schemas/changes'
import {
  changeSubjectRoute,
  changedFieldsLabel,
  conditionExplanation,
  stateExplanation,
} from './ChangesView.helpers'

const svc = inject(modelServiceKey)!

const changes = ref<readonly ChangeSummary[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const discarding = ref<string | null>(null)

const load = () => {
  loading.value = true
  error.value = null
  Effect.runPromise(svc.listChanges())
    .then((list) => { changes.value = list.changes })
    .catch((event: unknown) => { error.value = String(event) })
    .finally(() => { loading.value = false })
}

const discard = (change: ChangeSummary) => {
  discarding.value = change.artifact_id
  Effect.runPromise(svc.discardChange(change.artifact_id))
    .then(() => { load() })
    .catch((event: unknown) => { error.value = String(event) })
    .finally(() => { discarding.value = null })
}

onMounted(load)
</script>

<template>
  <section class="changes-page">
    <h1 class="changes-title">
      Local changes
    </h1>
    <p class="changes-intro">
      Edits to artifacts owned by the enterprise repository. They are held here until they are
      accepted upstream — this repository has nowhere to write them.
    </p>

    <p
      v-if="error"
      class="changes-error"
      role="alert"
    >
      {{ error }}
    </p>

    <p
      v-else-if="loading"
      class="changes-note"
    >
      Loading…
    </p>

    <p
      v-else-if="changes.length === 0"
      class="changes-note"
    >
      Nothing changed yet. Editing an artifact this repository does not own will show it here.
    </p>

    <ul
      v-else
      class="changes-list"
    >
      <li
        v-for="change in changes"
        :key="change.artifact_id"
        class="changes-row"
      >
        <div class="changes-row__subject">
          <RouterLink
            v-if="changeSubjectRoute(change)"
            :to="changeSubjectRoute(change)!"
            class="changes-row__link"
          >
            {{ change.target_name }}
          </RouterLink>
          <span
            v-else
            class="changes-row__link changes-row__link--plain"
          >{{ change.target_name }}</span>
          <span class="changes-row__kind">{{ change.kind }}</span>
        </div>

        <p class="changes-row__fields">
          Changes <strong>{{ changedFieldsLabel(change) }}</strong>
        </p>
        <p class="changes-row__state">
          {{ stateExplanation(change) }}
        </p>
        <p
          v-if="conditionExplanation(change)"
          class="changes-row__condition"
        >
          {{ conditionExplanation(change) }}
        </p>

        <button
          type="button"
          class="changes-row__discard"
          :disabled="discarding === change.artifact_id"
          @click="discard(change)"
        >
          {{ discarding === change.artifact_id ? 'Discarding…' : 'Discard' }}
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.changes-page { padding: 1rem 1.25rem; max-width: 60rem; }
.changes-title { font-size: 1.4rem; margin: 0 0 0.35rem; }
.changes-intro, .changes-note { color: var(--muted-fg, #555); margin: 0 0 1rem; }
.changes-error { color: var(--error-fg, #a11); margin: 0 0 1rem; }
.changes-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.75rem; }
.changes-row {
  border: 1px solid var(--border, #d8d8d8);
  border-radius: 6px;
  padding: 0.75rem 0.9rem;
  display: grid;
  gap: 0.25rem;
}
.changes-row__subject { display: flex; align-items: baseline; gap: 0.6rem; }
.changes-row__link { font-weight: 600; }
.changes-row__link--plain { color: var(--muted-fg, #555); }
.changes-row__kind {
  font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--muted-fg, #666);
}
.changes-row__fields, .changes-row__state, .changes-row__condition { margin: 0; font-size: 0.9rem; }
.changes-row__condition { color: var(--warning-fg, #8a5a00); }
.changes-row__discard { justify-self: start; margin-top: 0.35rem; }
</style>
