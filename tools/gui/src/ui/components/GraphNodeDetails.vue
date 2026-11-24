<script setup lang="ts">
import { entityGraphRoute } from '../router/artifactRoutes'
/** The exploration sidebar's node-detail card: identity fields, domain/status badges,
 * markdown content, and the explore-from-here link. Pure display over one loaded
 * `RenderedEntityDetail`. */
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RenderedEntityDetail } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { contentHtmlWithoutTitleHeading } from './entityContentHtml'
import { domainStyle } from '../lib/domains'

const props = defineProps<{
  detail: RenderedEntityDetail
  selectedId: string
}>()

const contentHtml = computed(() =>
  contentHtmlWithoutTitleHeading(props.detail.content_html, props.detail.name))
</script>

<template>
  <!-- No Name row: the panel's headline already shows the name, and links to the same page.
       Two identical links a line apart read as two different things to click. -->
  <div class="detail-field">
    <label>Type</label>
    <span class="detail-type">
      <ArchimateTypeGlyph
        :type="detail.artifact_type"
        :size="16"
        class="detail-glyph"
      />
      <span class="detail-value mono">{{ detail.artifact_type }}</span>
    </span>
  </div>
  <div class="detail-field">
    <label>Domain</label><span
      class="detail-value domain-badge domain-fill"
      :style="domainStyle(detail.domain)"
    >{{ detail.domain }}</span>
  </div>
  <div class="detail-field">
    <label>Status</label><span
      class="detail-value status-badge"
      :class="`status--${detail.status}`"
    >{{ detail.status }}</span>
  </div>
  <div class="detail-field">
    <label>Version</label><span class="detail-value">{{ detail.version }}</span>
  </div>
  <div class="detail-field">
    <label>Artifact ID</label><span class="detail-value mono id-value">{{ detail.artifact_id }}</span>
  </div>
  <div
    v-if="contentHtml"
    class="detail-content"
  >
    <label>Content</label>
    <!-- Server-rendered markdown from the entity's own content — same trust boundary as
         every other markdown surface. Its leading heading, which repeats the name shown
         above, is stripped; see `contentHtmlWithoutTitleHeading`. -->
    <!-- eslint-disable vue/no-v-html -->
    <div
      class="content-body markdown-body"
      v-html="contentHtml"
    />
    <!-- eslint-enable vue/no-v-html -->
  </div>
  <div class="detail-explore">
    <RouterLink
      :to="entityGraphRoute(selectedId)"
      class="explore-link"
    >
      Explore graph →
    </RouterLink>
  </div>
</template>

<style scoped>
.detail-field { margin-bottom: 12px; }
.detail-field label { display: block; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 2px; }
.detail-value { font-size: 13px; color: var(--text); }
.detail-type { display: inline-flex; align-items: center; gap: 8px; }
.detail-glyph { color: var(--text-2); fill: none; flex: 0 0 auto; }
.detail-link { font-weight: 600; }
.id-value { font-size: 11px; color: var(--faint); word-break: break-all; }
.mono { font-family: monospace; }
.detail-content { margin-top: 16px; }
.detail-content label { display: block; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
.content-body { font-size: 13px; line-height: 1.5; color: var(--text-2); max-height: 300px; overflow-y: auto; white-space: pre-wrap; }
.content-body :deep(p) { margin: 0.5rem 0; }
.detail-explore { margin-top: 12px; }
.explore-link { font-size: 12px; color: var(--accent); font-weight: 500; }
.domain-badge, .status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
/* Restated from `shared.css` because `.detail-value` here outranks the global badge colours. */
.detail-value.domain-fill { background: var(--domain); color: var(--on-domain); }
.status--draft       { background: var(--soft); color: var(--muted); }
.status--active      { background: var(--ok-soft); color: var(--ok-text); }
.status--deprecated  { background: var(--danger-soft); color: var(--danger-strong); }
</style>
