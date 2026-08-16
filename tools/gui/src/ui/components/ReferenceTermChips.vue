<script setup lang="ts">
import { formatReferenceTerm, type DocumentTypeLabel } from '../lib/documentSections'

/**
 * The terms one required- or suggested-connection list declares, as comma-separated chips.
 *
 * One component rather than the same seven lines of `v-for` and separator markup at each of the
 * four places a document type declares such a list — per type and per section, required and
 * suggested. `documentTypes` lets a `doc:` term show its declared name; the raw term stays in the
 * chip's title, so an author writing the schema can still see what to spell.
 */
defineProps<{
  terms: readonly string[]
  required?: boolean
  documentTypes?: readonly DocumentTypeLabel[]
}>()
</script>

<template>
  <span
    v-for="(term, index) in terms"
    :key="term"
    class="entity-type-tag"
    :class="{ 'entity-type-tag--required': required }"
    :title="term"
  >{{ formatReferenceTerm(term, documentTypes) }}<span
    v-if="index < terms.length - 1"
  >,&nbsp;</span></span>
</template>

<style scoped>
.entity-type-tag {
  font-family: monospace;
  font-size: 11px;
  background: rgba(0, 0, 0, .06);
  border-radius: 3px;
  padding: 1px 4px;
}
.entity-type-tag--required {
  background: rgba(220, 38, 38, .1);
}
</style>
