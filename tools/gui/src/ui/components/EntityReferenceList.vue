<script setup lang="ts">
/**
 * One "where does this appear" list on the entity detail view: a heading and linked rows.
 *
 * **It never learns which kind it is showing.** Three near-identical components stood here — one per
 * kind — and their own docstrings argued they had to, because "a single component switching on which
 * kind it was given would be a flag changing behaviour". That argument is right about a component
 * that *switches*, and this one cannot: it is handed rows already shaped for display and has no way
 * to ask what they came from. The vocabulary stays with the caller that owns it, which is where a
 * document's section, a diagram's type and a pad's silence about both are decided.
 *
 * What the three actually differed by was four values — a heading, a route prefix, a key and a meta
 * string — spelled out three times along with three copies of the same list markup and the same seven
 * style rules. A style rule that has to be corrected in three places is corrected in two.
 */

import type { EntityReferenceRow } from './entityReferenceRow'

defineProps<{ title: string; rows: readonly EntityReferenceRow[] }>()
</script>

<template>
  <div class="card reference-card">
    <h2 class="section-title">
      {{ title }}
    </h2>
    <ul class="reference-list">
      <li
        v-for="row in rows"
        :key="row.key"
        class="reference-item"
      >
        <RouterLink
          :to="{ path: row.to }"
          class="reference-title"
        >
          {{ row.name }}
        </RouterLink>
        <span
          v-if="row.meta"
          class="reference-meta"
        >{{ row.meta }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.reference-card { padding: 14px 16px; margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: #111827; }
.reference-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.reference-item { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.reference-title { font-size: 13px; font-weight: 600; color: #1d4ed8; }
.reference-meta { font-size: 12px; color: #64748b; }
</style>
