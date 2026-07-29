<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  failureModeHeadline,
  failureModeNeedsAttention,
  parseLensResponse,
  standaloneNodeLink,
} from './AssuranceLens.helpers'
import type { LensResult, RawLensResponse } from './AssuranceLens.helpers'
import { tlpColor } from './tlp'
import WithheldNotice from './WithheldNotice.vue'

const props = defineProps<{ artifactId: string }>()

const result = ref<LensResult | null>(null)

async function load(id: string) {
  try {
    const resp = await fetch(`/api/assurance/arch-lens/${encodeURIComponent(id)}`)
    if (resp.ok) {
      result.value = parseLensResponse(await resp.json() as RawLensResponse)
    }
  } catch {
    // additive lens — silent on failure; main view is unaffected
  }
}

onMounted(() => { void load(props.artifactId) })
watch(() => props.artifactId, (id) => { void load(id) })
</script>

<template>
  <!-- Locked or no data: render nothing so the main view is unaffected -->
  <template v-if="result && (result.visible || result.failureModes)">
    <div class="lens-section">
      <h3 class="lens-title">
        Assurance findings
      </h3>
      <WithheldNotice
        v-if="result.visibilityLimited"
        kind="findings"
      />
      <!-- The roll-up answers "is there anything here for me" without leaving this page. Rendered
           only when the element is a candidate at all: absent is not the same as nothing found. -->
      <p
        v-if="result.failureModes"
        class="lens-rollup"
        :class="{ 'lens-rollup-attention': failureModeNeedsAttention(result.failureModes) }"
      >
        {{ failureModeHeadline(result.failureModes) }}
      </p>
      <ul
        v-if="result.nodes.length"
        class="lens-list"
      >
        <li
          v-for="node in result.nodes"
          :key="node.node_id"
          class="lens-item"
        >
          <RouterLink
            :to="standaloneNodeLink(node.node_id)"
            class="lens-link"
          >
            <span class="lens-badge">{{ node.node_type }}</span>
            <span class="lens-name">{{ node.name }}</span>
            <span
              v-if="node.tlp && node.tlp !== 'TLP:WHITE'"
              class="lens-tlp"
              :style="{ color: tlpColor(node.tlp) }"
            >{{ node.tlp }}</span>
          </RouterLink>
        </li>
      </ul>
    </div>
  </template>
</template>

<style scoped>
.lens-section {
  margin-top: 24px;
  border-top: 1px solid #e2e8f0;
  padding-top: 16px;
}
.lens-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin: 0 0 10px;
}
.lens-rollup {
  font-size: 12px;
  color: #4b5563;
  margin: 0 0 10px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f1f5f9;
}
.lens-rollup-attention {
  background: #fef3c7;
  color: #92400e;
}
.lens-limited {
  font-size: 12px;
  color: #9ca3af;
  margin: 0 0 8px;
}
.lens-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lens-item {
  display: block;
}
.lens-link {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: inherit;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 13px;
}
.lens-link:hover {
  border-color: #2563eb;
  background: #eff6ff;
}
.lens-badge {
  font-size: 11px;
  font-weight: 500;
  background: #dbeafe;
  color: #1d4ed8;
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.lens-name {
  flex: 1;
  font-weight: 500;
}
.lens-tlp {
  font-size: 11px;
  font-weight: 600;
}
</style>
