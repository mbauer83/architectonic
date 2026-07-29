<script setup lang="ts">
/**
 * A collapsible navigation tree of arbitrary depth.
 *
 * Domain-agnostic by contract — it receives nodes that already carry their label, their badge and
 * the route they open, and it never imports architecture, assurance, viewpoint or ontology
 * concepts. The shape of a tree is the caller's knowledge, because the caller is the only party
 * that knows what its levels mean; this knows only that a node has a key, a label, maybe a route,
 * and maybe children.
 *
 * Recursive rather than a fixed number of levels: the architecture side files entities under a
 * framework group and a domain, the assurance side files nodes under a group and an analysis, and a
 * component that hard-coded either depth would be wrong for the other one first.
 *
 * `GroupedRowTree` is the flat-list counterpart — two levels over table rows, with click-to-select
 * instead of routes. This is the navigation counterpart: links, and as deep as the caller needs.
 */
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import type { NavTreeNode } from './NavTree.helpers'

const props = withDefaults(defineProps<{
  nodes: readonly NavTreeNode[]
  /** Nesting depth of `nodes`, used only for indentation. Callers start at 0. */
  depth?: number
  /** Highlighted node key, if any. */
  selectedKey?: string | null
  emptyMessage?: string
}>(), { depth: 0, selectedKey: null, emptyMessage: '' })

//: Keys the reader has explicitly toggled, and which way. Absent means "as the node declared",
//: so a caller's `collapsedByDefault` holds until someone touches that node.
const toggled = ref(new Map<string, boolean>())

const isExpanded = (node: NavTreeNode): boolean =>
  toggled.value.get(node.key) ?? !node.collapsedByDefault

const toggle = (node: NavTreeNode): void => {
  const next = new Map(toggled.value)
  next.set(node.key, !isExpanded(node))
  toggled.value = next
}

const hasChildren = (node: NavTreeNode): boolean => (node.children?.length ?? 0) > 0
</script>

<template>
  <p
    v-if="props.nodes.length === 0 && props.emptyMessage"
    class="nav-tree__empty"
  >
    {{ props.emptyMessage }}
  </p>
  <ul
    v-else
    class="nav-tree"
  >
    <li
      v-for="node in props.nodes"
      :key="node.key"
      class="nav-tree__item"
    >
      <div
        class="nav-tree__row"
        :class="{ 'nav-tree__row--selected': props.selectedKey === node.key }"
        :style="{ paddingLeft: `${14 + props.depth * 12}px` }"
      >
        <button
          v-if="hasChildren(node)"
          type="button"
          class="nav-tree__caret"
          :aria-expanded="isExpanded(node)"
          :aria-label="`${isExpanded(node) ? 'Collapse' : 'Expand'} ${node.label}`"
          @click="toggle(node)"
        >
          {{ isExpanded(node) ? '▾' : '▸' }}
        </button>
        <span
          v-else
          class="nav-tree__caret nav-tree__caret--none"
        />

        <RouterLink
          v-if="node.to"
          :to="node.to"
          class="nav-tree__label nav-tree__label--link"
        >
          {{ node.label }}
        </RouterLink>
        <button
          v-else-if="hasChildren(node)"
          type="button"
          class="nav-tree__label nav-tree__label--heading"
          @click="toggle(node)"
        >
          {{ node.label }}
        </button>
        <span
          v-else
          class="nav-tree__label"
        >{{ node.label }}</span>

        <span
          v-if="node.badge"
          class="nav-tree__badge"
        >{{ node.badge }}</span>
      </div>

      <NavTree
        v-if="hasChildren(node) && isExpanded(node)"
        :nodes="node.children!"
        :depth="props.depth + 1"
        :selected-key="props.selectedKey"
      />
    </li>
  </ul>
</template>

<style scoped>
.nav-tree { list-style: none; margin: 0; padding: 0; }
.nav-tree__empty { font-size: 12px; color: #6b7280; padding: 6px 14px; margin: 0; }
.nav-tree__row { display: flex; align-items: center; gap: 4px; padding-right: 10px; }
.nav-tree__row:hover { background: #f3f4f6; }
.nav-tree__row--selected { background: #eff6ff; }
.nav-tree__caret {
  background: none; border: none; cursor: pointer; color: #9ca3af;
  width: 14px; flex-shrink: 0; padding: 0; font-size: 10px; line-height: 1;
}
.nav-tree__caret--none { cursor: default; }
.nav-tree__label {
  flex: 1; min-width: 0; text-align: left; background: none; border: none;
  font-size: 12.5px; color: #374151; text-decoration: none;
  padding: 4px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.nav-tree__label--heading { cursor: pointer; font-weight: 600; }
.nav-tree__label--link { cursor: pointer; }
.nav-tree__label--link:hover { color: #1d4ed8; }
.nav-tree__row--selected .nav-tree__label { color: #1d4ed8; font-weight: 600; }
.nav-tree__badge {
  font-size: 10px; font-weight: 600; color: #6b7280; background: #f1f5f9;
  border-radius: 8px; padding: 1px 6px; flex-shrink: 0;
}
</style>
