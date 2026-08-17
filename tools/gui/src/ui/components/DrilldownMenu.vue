<script setup lang="ts">
/**
 * "Drill into this, as…" — the choice a node offers when it has more than one view below it.
 *
 * A container may be drawn one concern at a time: a write path, a read path, an assurance module.
 * None of those is the main one, so there is no tie-break to apply and the reader picks. The same
 * shape as the download control, for the same reason — one affordance, several answers, and the
 * surface decides what choosing means.
 *
 * Positioned at the click rather than anchored to a button: the badge that opens this lives inside
 * the rendered SVG, which has its own coordinate space and no Vue element to attach a dropdown to.
 */
import type { DrilldownTarget } from '../views/DiagramDetailView.helpers'

const props = defineProps<{ targets: readonly DrilldownTarget[]; x: number; y: number; scopeName?: string | null }>()
const emit = defineEmits<{ choose: [target: DrilldownTarget]; dismiss: [] }>()

/**
 * The part of a view's name that distinguishes it here.
 *
 * Every view below one container is named for that container — "Architecture Backend — Write Path"
 * — so inside a menu opened from *that node* the prefix is the one thing every option shares. Trim
 * it and the options read as what they are; keep it and the reader compares the same three words
 * six times. The name to trim is the clicked node's, not the diagram's own scope: a container view
 * is scoped to the system, while the badge sits on one of its containers.
 */
const label = (name: string): string => {
  const scope = props.scopeName
  if (!scope) return name
  const prefix = `${scope} — `
  return name.startsWith(prefix) ? name.slice(prefix.length) : name
}
</script>

<template>
  <div
    class="dd-overlay"
    @click.stop="emit('dismiss')"
  />
  <div
    class="dd-menu"
    role="menu"
    :style="{ left: `${x}px`, top: `${y}px` }"
  >
    <div class="dd-head">
      Drill down to
    </div>
    <button
      v-for="target in targets"
      :key="target.diagramId"
      class="dd-opt"
      role="menuitem"
      @click.stop="emit('choose', target)"
    >
      {{ label(target.name) }}
    </button>
  </div>
</template>

<style scoped>
.dd-overlay { position: fixed; inset: 0; z-index: 40; }
.dd-menu {
  position: fixed; z-index: 41; background: white; border: 1px solid #e5e7eb;
  border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,.12); min-width: 190px; overflow: hidden;
}
.dd-head {
  padding: 6px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: #9ca3af; border-bottom: 1px solid #f3f4f6;
}
.dd-opt {
  display: block; width: 100%; text-align: left; padding: 7px 12px;
  background: none; border: none; font-size: 13px; cursor: pointer; color: #374151;
}
.dd-opt:hover { background: #f9fafb; }
</style>
