<script setup lang="ts">
/**
 * The open candidate architectures that read over some of the same model elements as the naive architecture
 * (06·0), so an analyst sees work already under way on them. What the naive reads over is what it was
 * sketched over on its canvas; candidates in its own stack are not listed.
 */
import { computed } from 'vue'
import type { CandidateSummary } from '../../../domain/schemas/candidates'
import { touchingScope } from '../../../domain/candidates/touchingScope'
import { candidateDetailRoute } from '../../router/artifactRoutes'

const props = defineProps<{
  scope: readonly string[]
  candidates: readonly CandidateSummary[]
  /** The naive architecture's own stack, which is not "other work". */
  own: readonly string[]
}>()

const touching = computed(() =>
  touchingScope(props.scope, props.candidates.filter((one) => !props.own.includes(one.id))))
</script>

<template>
  <section
    v-if="touching.length"
    class="touching"
    data-testid="touching-candidates"
    aria-label="Open candidates touching the naive architecture"
  >
    <h3>Open candidate architectures reading over these elements</h3>
    <ul>
      <li
        v-for="one in touching"
        :key="one.candidate.id"
      >
        <RouterLink :to="candidateDetailRoute(one.candidate.id)">
          {{ one.candidate.name }}
        </RouterLink>
        <small>{{ one.candidate.state }} · reads {{ one.shared }} of them</small>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.touching { border-top: 1px solid var(--border); padding: 6px 10px; font-size: 12px; }
.touching h3 { font-size: 12px; margin: 0 0 4px; }
.touching ul { margin: 0; padding-left: 16px; }
.touching small { color: var(--muted); margin-left: 6px; }
</style>
