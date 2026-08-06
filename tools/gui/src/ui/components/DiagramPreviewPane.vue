<script setup lang="ts">
/**
 * The right-hand pane of the diagram authoring flow: what the write would produce.
 *
 * Its own component for the reason the entity create view's pane is: it renders a `DiagramPreview`
 * and knows nothing about how one was requested, so the view above it keeps only the authoring
 * form. `showPuml` is local — whether the source is unfolded is this pane's business and nothing
 * else's.
 */
import { ref } from 'vue'
import PreviewViewport from './PreviewViewport.vue'
import DerivedEntityChecklist from './DerivedEntityChecklist.vue'
import type { DiagramPreviewResult } from '../../domain/schemas'

defineProps<{
  preview: DiagramPreviewResult | null
  previewBusy: boolean
  previewError: string | null
  previewClean: boolean
  previewIssues: readonly string[]
  excludedEntityIds: ReadonlySet<string>
  entitySearchFilter: boolean
}>()

const emit = defineEmits<{ 'toggle-exclusion': [string] }>()

const showPuml = ref(false)
</script>

<template>
  <div
    v-if="!preview && !previewBusy && !previewError"
    class="preview-hint"
  >
    {{ entitySearchFilter ? 'Select entities and connections, then click' : 'Configure the diagram, then click' }}
    <strong>Preview</strong>.
  </div>
  <div
    v-if="previewBusy"
    class="state-msg"
  >
    Rendering…
  </div>
  <div
    v-if="previewError"
    class="state-err"
  >
    {{ previewError }}
  </div>

  <template v-if="preview">
    <div
      v-if="!previewClean"
      class="state-err"
    >
      <strong>Verification issues found:</strong>
      <ul style="margin-top: 4px; font-size: 12px; margin-bottom: 0; padding-left: 18px;">
        <li
          v-for="issue in previewIssues"
          :key="issue"
        >
          {{ issue }}
        </li>
      </ul>
    </div>
    <div
      v-else
      class="state-msg"
    >
      Verification passed.
    </div>
    <PreviewViewport
      v-if="preview.image"
      :reset-signal="preview"
    >
      <img
        :src="preview.image"
        class="preview-img"
        alt="Diagram preview"
        draggable="false"
      >
    </PreviewViewport>
    <div
      v-else
      class="state-msg"
    >
      No image could be rendered.
      <ul
        v-if="preview.warnings.length"
        class="render-warnings"
      >
        <li
          v-for="w in preview.warnings"
          :key="w"
        >
          {{ w }}
        </li>
      </ul>
    </div>
    <!-- Derived entity checklist (model-backed C4) -->
    <DerivedEntityChecklist
      v-if="preview.derived_entities !== null && preview.derived_entities !== undefined"
      :derived="preview.derived_entities"
      :excluded-ids="excludedEntityIds"
      @toggle="emit('toggle-exclusion', $event)"
    />

    <button
      class="toggle-src"
      @click="showPuml = !showPuml"
    >
      {{ showPuml ? 'Hide' : 'Show' }} PUML source
    </button>
    <pre
      v-if="showPuml"
      class="puml-src"
    >{{ preview.puml }}</pre>
  </template>
</template>

<style scoped>
.preview-hint { font-size: 13px; color: #9ca3af; }
/* Fit the whole diagram on open; the viewport's pan/zoom magnifies from there. */
.preview-img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }
.render-warnings { margin: 6px 0 0 0; padding-left: 18px; font-size: 12px; color: #b45309; }
.state-msg { font-size: 13px; color: #6b7280; margin-bottom: 10px; }
.state-err { font-size: 13px; color: #b91c1c; margin-bottom: 10px; }
.toggle-src {
  margin-top: 10px; font-size: 12px; background: none;
  border: none; color: #2563eb; cursor: pointer; padding: 0;
}
.puml-src {
  margin-top: 8px; font-size: 11px; background: #f9fafb;
  border: 1px solid #e5e7eb; border-radius: 4px; padding: 8px;
  overflow: auto; max-height: 320px;
}
</style>
