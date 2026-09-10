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
 *
 * A stale row shows both values, artifact first and the author's second. "Stale" alone says the work
 * needs attention and nothing about what to do — an author would otherwise have to open the
 * enterprise artifact, if they can reach it at all, and compare by eye.
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { ChangeSummary } from '../../domain/schemas/changes'
import {
  canBeRebased,
  changeSubjectRoute,
  changedFieldsLabel,
  conditionExplanation,
  divergenceKey,
  isLongValue,
  rebaseOutcomeMessage,
  stateExplanation,
  submitLabel,
  submittableIds,
} from './ChangesView.helpers'

const svc = inject(modelServiceKey)!

const changes = ref<readonly ChangeSummary[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const discarding = ref<string | null>(null)
const rebasing = ref<string | null>(null)
// What the last rebase concluded, by change, so a reader sees the answer beside the row.
const rebased = ref<Record<string, string>>({})
// Which long values the reader has asked to see whole, by change and field.
const expanded = ref(new Set<string>())
const toggle = (key: string) => {
  const next = new Set(expanded.value)
  if (!next.delete(key)) next.add(key)
  expanded.value = next
}

const submitting = ref(false)
// What the last submission said, and what it refused. Kept apart from `error`, which is about
// loading the page: a refusal to submit leaves the list perfectly readable.
const submitted = ref<string | null>(null)
const submitRefusal = ref<string | null>(null)
const submittable = computed(() => submittableIds(changes.value))

const submit = () => {
  submitting.value = true
  submitted.value = null
  submitRefusal.value = null
  Effect.runPromise(svc.submitChanges(submittable.value))
    .then((report) => { submitted.value = report.summary; load() })
    .catch((event: unknown) => { submitRefusal.value = String(event) })
    .finally(() => { submitting.value = false })
}

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

const rebase = (change: ChangeSummary) => {
  rebasing.value = change.artifact_id
  Effect.runPromise(svc.rebaseChange(change.artifact_id))
    .then((report) => {
      const first = report.changes[0]
      rebased.value = {
        ...rebased.value,
        [change.artifact_id]: first
          ? rebaseOutcomeMessage(first.outcome, first.reason)
          : report.summary,
      }
      load()
    })
    .catch((event: unknown) => { error.value = String(event) })
    .finally(() => { rebasing.value = null })
}

onMounted(load)
</script>

<template>
  <section class="changes-page">
    <h1 class="changes-title">
      Proposed changes
    </h1>
    <p class="changes-intro">
      Edits to artifacts owned by the enterprise repository. They are held here until they are
      accepted upstream — this repository has nowhere to write them.
    </p>

    <div
      v-if="submittable.length > 0"
      class="changes-submit"
    >
      <button
        type="button"
        class="changes-submit__button"
        :disabled="submitting"
        @click="submit"
      >
        {{ submitting ? 'Submitting…' : submitLabel(submittable.length) }}
      </button>
      <span class="changes-submit__hint">
        Replays them into the enterprise repository and publishes the branch a reviewer reads.
      </span>
    </div>

    <p
      v-if="submitted"
      class="changes-note changes-note--done"
      role="status"
    >
      {{ submitted }}
    </p>

    <p
      v-if="submitRefusal"
      class="changes-error"
      role="alert"
    >
      {{ submitRefusal }}
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
            :to="changeSubjectRoute(change)"
            class="changes-row__link"
          >
            {{ change.target_name }}
          </RouterLink>
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
        <dl
          v-if="change.divergence.length > 0"
          class="changes-row__divergence"
        >
          <template
            v-for="side in change.divergence"
            :key="side.field"
          >
            <dt class="changes-row__field">
              {{ side.field }}
            </dt>
            <dd class="changes-row__values">
              <span
                class="changes-row__value changes-row__value--theirs"
                :class="{
                  'changes-row__value--clamped':
                    isLongValue(side.current)
                    && !expanded.has(divergenceKey(change.artifact_id, side.field)),
                }"
              >{{ side.current ?? 'not shown here' }}</span>
              <span class="changes-row__arrow">→</span>
              <span class="changes-row__value changes-row__value--mine">
                {{ side.proposed ?? 'not shown here' }}
              </span>
              <button
                v-if="isLongValue(side.current)"
                type="button"
                class="changes-row__expand"
                @click="toggle(divergenceKey(change.artifact_id, side.field))"
              >
                {{ expanded.has(divergenceKey(change.artifact_id, side.field))
                  ? 'Show less' : 'Show the whole current value' }}
              </button>
            </dd>
          </template>
        </dl>

        <p
          v-if="rebased[change.artifact_id]"
          class="changes-row__rebased"
        >
          {{ rebased[change.artifact_id] }}
        </p>

        <div class="changes-row__actions">
          <button
            v-if="canBeRebased(change)"
            type="button"
            class="changes-row__discard"
            :disabled="rebasing === change.artifact_id"
            @click="rebase(change)"
          >
            {{ rebasing === change.artifact_id ? 'Rebasing…' : 'Bring onto the current version' }}
          </button>
          <button
            type="button"
            class="changes-row__discard"
            :disabled="discarding === change.artifact_id"
            @click="discard(change)"
          >
            {{ discarding === change.artifact_id ? 'Discarding…' : 'Discard' }}
          </button>
        </div>
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
.changes-row__kind {
  font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--muted-fg, #666);
}
.changes-row__fields, .changes-row__state, .changes-row__condition { margin: 0; font-size: 0.9rem; }
.changes-row__condition { color: var(--warning-fg, #8a5a00); }
.changes-row__divergence {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.15rem 0.75rem;
  margin: 0.35rem 0 0;
  font-size: 0.85rem;
}
.changes-row__field { font-weight: 600; color: var(--muted-fg, #555); }
.changes-row__values { margin: 0; display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
.changes-row__value { flex: 1 1 18rem; min-width: 0; }
.changes-row__value--theirs { color: var(--muted-fg, #666); text-decoration: line-through; }
.changes-row__value--clamped {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.changes-row__expand {
  background: none; border: 0; padding: 0;
  color: var(--link-fg, #2563eb); cursor: pointer; font: inherit; text-decoration: underline;
}
.changes-row__value--mine { color: var(--fg, #111); }
.changes-row__arrow { color: var(--muted-fg, #888); }
/* The same treatment the entity delete panel's cancel gives a reversible-looking action: this
   ends a change rather than deleting an artifact, so it is not the red one. */
.changes-row__actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.changes-row__rebased { margin: 0.35rem 0 0; font-size: 0.85rem; color: var(--muted-fg, #555); }
.changes-row__discard {
  justify-self: start;
  margin-top: 0.5rem;
  padding: 7px 16px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.changes-row__discard:hover:not(:disabled) { background: #e5e7eb; }
.changes-row__discard:disabled { opacity: 0.5; cursor: not-allowed; }

/* The one action on this page that reaches outside the repository, so it is the one that reads as
   primary. Everything else here is local and takes the quiet treatment the row buttons have. */
.changes-submit {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}
.changes-submit__button {
  padding: 8px 18px;
  background: #1f2937;
  color: #f9fafb;
  border: 1px solid #1f2937;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.changes-submit__button:hover:not(:disabled) { background: #111827; }
.changes-submit__button:disabled { opacity: 0.5; cursor: not-allowed; }
.changes-submit__hint { color: #6b7280; font-size: 13px; }
.changes-note--done { color: #065f46; }
</style>
