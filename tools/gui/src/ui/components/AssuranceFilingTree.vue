<script setup lang="ts">
/**
 * The filing tree in the assurance nav: which group each analysis is in, and what each analysis
 * wrote.
 *
 * The analogue of the architecture side's group nav tree, and the reason the left nav is worth
 * having: without it the only route to an analysis is a picker above the node list, so "what
 * analyses exist and what is in them" is a question the surface could not answer at a glance.
 *
 * Three requests, not one per analysis: groups, analyses, and the whole visible node list, joined
 * here. A request per analysis would turn opening a nav into a dozen round trips against an
 * encrypted store.
 *
 * A locked store is not an error here. The nav sits beside content that says so already, and a
 * second red message in the sidebar adds nothing.
 */
import { computed, onMounted, ref } from 'vue'
import NavTree from './NavTree.vue'
import {
  buildFilingTree,
  type AssuranceAnalysis,
  type AssuranceGroup,
  type AssuranceTreeNode,
} from './AssuranceFilingTree.helpers'

const props = defineProps<{
  /** Highlighted analysis, so the tree agrees with the list beside it. */
  selectedKey?: string | null
}>()

const groups = ref<AssuranceGroup[]>([])
const analyses = ref<AssuranceAnalysis[]>([])
const nodes = ref<AssuranceTreeNode[]>([])
const loading = ref(true)
const locked = ref(false)

const tree = computed(() => buildFilingTree(groups.value, analyses.value, nodes.value))

async function readList<T>(url: string, key: string): Promise<T[]> {
  const response = await fetch(url)
  if (response.status === 423) {
    locked.value = true
    return []
  }
  if (!response.ok) return []
  const body = await response.json() as Record<string, unknown>
  const list = body[key]
  return Array.isArray(list) ? list as T[] : []
}

onMounted(async () => {
  try {
    const [loadedGroups, loadedAnalyses, loadedNodes] = await Promise.all([
      readList<AssuranceGroup>('/api/assurance/groups', 'groups'),
      readList<AssuranceAnalysis>('/api/assurance/analyses', 'analyses'),
      readList<AssuranceTreeNode>('/api/assurance/nodes', 'nodes'),
    ])
    groups.value = loadedGroups
    analyses.value = loadedAnalyses
    nodes.value = loadedNodes
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="filing-tree">
    <p
      v-if="loading"
      class="filing-tree__state"
    >
      Loading…
    </p>
    <p
      v-else-if="locked"
      class="filing-tree__state"
    >
      Store locked.
    </p>
    <NavTree
      v-else
      :nodes="tree"
      :selected-key="props.selectedKey ?? null"
      empty-message="No analyses yet. Start one above."
    />
  </div>
</template>

<style scoped>
.filing-tree { padding: 2px 0; }
.filing-tree__state { font-size: 12px; color: #6b7280; padding: 4px 14px; margin: 0; }
</style>
