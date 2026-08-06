<script setup lang="ts">
/**
 * The first-degree neighbours one *drawing* can pull into the diagram.
 *
 * Offered per drawing rather than per entity: including a neighbour from an occurrence's panel
 * connects it to that copy of the cluster and no other, which is the only way a second drawing ever
 * gets a neighbourhood of its own.
 */
import type { EntityDisplayInfo } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'

defineProps<{
  entities: readonly EntityDisplayInfo[]
  /** Whether this is an occurrence's panel, which changes what including one promises. */
  occurrence?: boolean
}>()

const emit = defineEmits<{ include: [entity: EntityDisplayInfo] }>()
</script>

<template>
  <div class="entity-panel entity-panel--related">
    <div
      v-if="!entities.length"
      class="empty-msg"
    >
      No non-included first-degree related entities.
    </div>
    <div
      v-else
      class="related-list"
    >
      <div
        v-for="entity in entities"
        :key="entity.artifact_id"
        class="related-row"
      >
        <span
          class="dd-glyph"
          :title="entity.element_type || entity.artifact_type"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(entity.element_type || entity.artifact_type)"
            :size="13"
          />
        </span>
        <span class="related-name">{{ entity.name }}</span>
        <span class="related-domain">{{ entity.domain }}</span>
        <button
          class="include-btn"
          :title="occurrence ? 'Add this entity and connect it to this occurrence' : 'Include entity'"
          @click="emit('include', entity)"
        >
          +
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.entity-panel {
  padding: 6px 8px 8px 26px; background: #fbfbfc; border-bottom: 1px solid #f1f3f5;
}
.entity-panel--related { background: #fcfcfd; }
.empty-msg { font-size: 11px; color: #9ca3af; font-style: italic; }
.related-list { display: flex; flex-direction: column; gap: 3px; }
.related-row { display: flex; align-items: center; gap: 6px; min-height: 22px; }
.dd-glyph { display: inline-flex; align-items: center; flex-shrink: 0; }
.related-name {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 12px; color: #374151;
}
.related-domain { font-size: 10px; color: #9ca3af; }
.include-btn {
  width: 20px; height: 20px; border-radius: 4px; border: 1px solid #d1d5db;
  background: white; color: #374151; cursor: pointer; line-height: 1; flex-shrink: 0;
}
.include-btn:hover { border-color: #86efac; color: #15803d; }
</style>
