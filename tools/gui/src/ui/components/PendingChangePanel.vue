<script setup lang="ts">
/**
 * What this repository has changed about an artifact it does not own, shown on the artifact itself.
 *
 * The badge says *which* fields differ; this says what they now say. Without it an author's own
 * pending values are visible nowhere they would look: the artifact's rendered body is the enterprise
 * text (or, for a reference, its proxy stub), and the values reach the screen only if they reopen
 * the edit form.
 *
 * It reads the changes list rather than taking values from the detail payload, because a change
 * against a *document* speaks `title` and `body` — fields an entity payload has never heard of and
 * its closed contract refuses. One reading serves all three kinds.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { ChangeSummary } from '../../domain/schemas/changes'
import { isProposed, type BaselineStanding } from '../../domain/schemas/baselineStanding'
import { changesAgainst } from './PendingChangePanel.helpers'

const props = defineProps<{ standing: BaselineStanding; artifactId: string }>()

const svc = inject(modelServiceKey)!
const changes = ref<readonly ChangeSummary[]>([])

const mine = computed(() => changesAgainst(changes.value, props.artifactId))

const load = () => {
  if (!isProposed(props.standing)) {
    changes.value = []
    return
  }
  Effect.runPromise(svc.listChanges())
    .then((list) => { changes.value = list.changes })
    // A panel that cannot load is a panel that shows nothing: the badge has already said the
    // artifact carries a change, and an error here would be a second, louder statement of a
    // problem the reader cannot act on.
    .catch(() => { changes.value = [] })
}

onMounted(load)
watch(() => [props.artifactId, props.standing] as const, load)
</script>

<template>
  <section
    v-if="mine.length > 0"
    class="pending"
    aria-label="Your pending changes to this artifact"
  >
    <h2 class="pending__title">
      Not yet accepted upstream
    </h2>
    <p class="pending__intro">
      This artifact belongs to the enterprise repository. These edits are held here until they are
      accepted there — what you see below is what they would make it say.
    </p>
    <dl
      v-for="change in mine"
      :key="change.artifact_id"
      class="pending__fields"
    >
      <template
        v-for="side in change.divergence"
        :key="side.field"
      >
        <dt class="pending__field">
          {{ side.field }}
        </dt>
        <dd class="pending__value">
          {{ side.proposed ?? 'changed; not shown as text here' }}
        </dd>
      </template>
    </dl>
  </section>
</template>

<style scoped>
.pending {
  border: 1px solid #fcd34d;
  background: #fffbeb;
  border-radius: 6px;
  padding: 0.75rem 0.9rem;
  margin-bottom: 1rem;
}
.pending__title { font-size: 0.95rem; margin: 0 0 0.25rem; }
.pending__intro { margin: 0 0 0.6rem; font-size: 0.85rem; color: #78350f; }
.pending__fields { display: grid; grid-template-columns: auto 1fr; gap: 0.2rem 0.75rem; margin: 0; }
.pending__field { font-weight: 600; font-size: 0.85rem; color: #78350f; }
.pending__value { margin: 0; font-size: 0.9rem; white-space: pre-wrap; }
</style>
