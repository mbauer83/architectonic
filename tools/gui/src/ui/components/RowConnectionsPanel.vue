<script setup lang="ts">
/**
 * The connections one drawing carries, included beside excluded, grouped by relation type.
 *
 * Split out of the selection list so the list stays about *rows*; what a row unfolds into is this.
 * Clicking an entry toggles that connection on this drawing — the list decides what toggling means
 * for the base drawing versus a further occurrence, so the panel only reports which connection.
 */
import type { ConnTypeGroup } from '../lib/rowConnections'

defineProps<{
  groups: Array<[string, ConnTypeGroup]>
  /** Whether this is a further drawing of the entity, which changes what an empty list means. */
  occurrence: boolean
}>()

const emit = defineEmits<{
  toggle: [connectionId: string]
}>()
</script>

<template>
  <div class="entity-panel">
    <div
      v-if="!groups.length"
      class="empty-msg"
    >
      {{ occurrence
        ? 'No unclaimed connections — each is already drawn on another occurrence of this entity.'
        : 'No connections to currently included entities.' }}
    </div>
    <div
      v-for="[connType, group] in groups"
      :key="connType"
      class="conn-type-block"
    >
      <div class="conn-type-label">
        {{ connType }}
      </div>
      <div class="conn-cols">
        <div class="conn-col">
          <div class="col-header col-header--included">
            Included
          </div>
          <button
            v-for="entry in group.included"
            :key="entry.conn.artifact_id"
            class="conn-entry conn-entry--included"
            title="Exclude connection"
            @click="emit('toggle', entry.conn.artifact_id)"
          >
            <span class="dir-arrow">{{ entry.direction === 'out' ? '→' : '←' }}</span>
            <span class="other-name">{{ entry.otherName }}</span>
          </button>
          <div
            v-if="!group.included.length"
            class="col-empty"
          >
            —
          </div>
        </div>
        <div class="conn-col">
          <div class="col-header">
            Excluded
          </div>
          <button
            v-for="entry in group.excluded"
            :key="entry.conn.artifact_id"
            class="conn-entry conn-entry--excluded"
            :title="occurrence ? 'Draw this connection on this occurrence' : 'Include connection'"
            @click="emit('toggle', entry.conn.artifact_id)"
          >
            <span class="dir-arrow">{{ entry.direction === 'out' ? '→' : '←' }}</span>
            <span class="other-name">{{ entry.otherName }}</span>
          </button>
          <div
            v-if="!group.excluded.length"
            class="col-empty"
          >
            —
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.entity-panel { padding: 10px; border-top: 1px solid #f3f4f6; background: #fafafa; }
.empty-msg { font-size: 12px; color: #9ca3af; }
.conn-type-block + .conn-type-block { margin-top: 8px; }
.conn-type-label {
  font-size: 10px; font-weight: 700; color: #6366f1; text-transform: uppercase;
  letter-spacing: .04em; margin-bottom: 4px;
}
.conn-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.conn-col { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.col-header { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }
.col-header--included { color: #059669; }
.conn-entry {
  display: flex; align-items: center; gap: 6px; width: 100%; text-align: left; padding: 6px 8px; border-radius: 6px;
  font-size: 12px; border: none; background: none; cursor: pointer;
}
.conn-entry--included { background: #ecfdf5; color: #1f2937; }
.conn-entry--included:hover { background: #d1fae5; }
.conn-entry--excluded { background: #fff; color: #6b7280; border: 1px solid #e5e7eb; }
.conn-entry--excluded:hover { background: #f9fafb; color: #1f2937; }
.dir-arrow { color: #6b7280; flex-shrink: 0; }
.col-empty { font-size: 11px; color: #d1d5db; padding: 6px 8px; }
.other-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
