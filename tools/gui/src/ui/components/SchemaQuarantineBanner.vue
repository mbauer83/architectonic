<script setup lang="ts">
/** Banner for a quarantined (entity-type, specialization) pair: names the pair, lists the
 * conflicting declarations the endpoint reported, and states the remedy. Pure display —
 * the authoring form owns disabling its own submit. */
import { computed } from 'vue'
import { QUARANTINE_REMEDY, quarantineHeadline, type SchemaQuarantine } from '../lib/schemaQuarantine'

const props = withDefaults(defineProps<{
  quarantine: SchemaQuarantine
  artifactType: string
  specialization?: string
}>(), { specialization: '' })

const headline = computed(() => quarantineHeadline(props.artifactType, props.specialization))
</script>

<template>
  <div
    v-if="quarantine.quarantined"
    class="quarantine"
    role="alert"
  >
    <p class="quarantine-lead">
      <strong>{{ headline }}.</strong> {{ QUARANTINE_REMEDY }}
    </p>
    <ul
      v-if="quarantine.conflicts.length > 0"
      class="quarantine-list"
    >
      <li
        v-for="conflict in quarantine.conflicts"
        :key="conflict"
      >
        {{ conflict }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.quarantine { border: 1px solid #fecaca; background: #fef2f2; border-radius: 6px; padding: 8px 12px; margin: 4px 0; }
.quarantine-lead { margin: 0; font-size: 12.5px; color: #991b1b; }
.quarantine-list { list-style: disc; margin: 6px 0 0; padding-left: 18px; }
.quarantine-list li { font-size: 12px; color: #991b1b; font-family: ui-monospace, monospace; }
</style>
