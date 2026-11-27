<script setup lang="ts">
/** Who a diagram is for and what it answers: "For … · Answers …", each referenced element a link to its page. */
import type { DiagramPurpose, PurposeEntryShown } from '../../domain/purposeLines'
import { entityDetailRoute } from '../router/artifactRoutes'

defineProps<{ purpose: DiagramPurpose }>()

const sections = (purpose: DiagramPurpose): { label: string; entries: readonly PurposeEntryShown[] }[] =>
  [
    { label: 'For', entries: purpose.stakeholders },
    { label: 'Answers', entries: purpose.concerns },
  ].filter((section) => section.entries.length > 0)
</script>

<template>
  <p
    class="purpose-line"
    data-testid="diagram-purpose-line"
  >
    <template
      v-for="(section, index) in sections(purpose)"
      :key="section.label"
    >
      <span
        v-if="index > 0"
        class="sep"
      > · </span>
      <span class="label">{{ `${section.label} ` }}</span>
      <template
        v-for="(entry, position) in section.entries"
        :key="`${section.label}-${position}`"
      >
        <span v-if="position > 0">, </span>
        <RouterLink
          v-if="entry.ref"
          :to="entityDetailRoute(entry.ref)"
        >
          {{ entry.text }}
        </RouterLink>
        <span v-else>{{ entry.text }}</span>
      </template>
    </template>
    <span
      v-if="purpose.inherited_from"
      class="inherited"
      :title="`Lines this diagram does not state are taken from the viewpoint '${purpose.inherited_from}'`"
    > (from viewpoint {{ purpose.inherited_from }})</span>
  </p>
</template>

<style scoped>
.purpose-line { margin: -6px 0 14px; font-size: 13px; color: var(--text); }
.label { font-weight: 600; }
.sep, .inherited { color: var(--faint); }
</style>
