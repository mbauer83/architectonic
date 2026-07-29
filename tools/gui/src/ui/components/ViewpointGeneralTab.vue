<script setup lang="ts">
/**
 * "General" tab of the viewpoint definition editor: identity + purpose/content/
 * stakeholders/concerns. Read-only `draft` in, a patch emitted out — the parent applies it
 * to its own draft ref (never mutate a prop directly, `vue/no-mutating-props`).
 */
import { VALID_CONTENTS, VALID_PURPOSES } from '../../domain/viewpointDefinitionDraft'
import type { ViewpointDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import { csvToList, listToCsv } from '../views/ViewpointsManagementView.helpers'

const props = defineProps<{
  draft: ViewpointDefinitionDraft
  isCreating: boolean
}>()
const emit = defineEmits<{ update: [patch: Partial<ViewpointDefinitionDraft>] }>()

const togglePurpose = (value: (typeof VALID_PURPOSES)[number]) => {
  emit('update', {
    purpose: props.draft.purpose.includes(value)
      ? props.draft.purpose.filter((v) => v !== value)
      : [...props.draft.purpose, value],
  })
}
const toggleContent = (value: (typeof VALID_CONTENTS)[number]) => {
  emit('update', {
    content: props.draft.content.includes(value)
      ? props.draft.content.filter((v) => v !== value)
      : [...props.draft.content, value],
  })
}
</script>

<template>
  <div>
    <label class="field">
      slug
      <input
        :value="draft.slug"
        class="inp"
        :disabled="!isCreating"
        @input="emit('update', { slug: ($event.target as HTMLInputElement).value })"
      >
    </label>
    <label class="field">
      version
      <input
        :value="draft.version"
        class="inp"
        type="number"
        @input="emit('update', { version: Number(($event.target as HTMLInputElement).value) })"
      >
    </label>
    <label class="field">
      name
      <input
        :value="draft.name"
        class="inp"
        @input="emit('update', { name: ($event.target as HTMLInputElement).value })"
      >
    </label>
    <label class="field">
      description
      <textarea
        :value="draft.description"
        class="inp"
        @input="emit('update', { description: ($event.target as HTMLTextAreaElement).value })"
      />
    </label>
    <label class="field">
      rationale
      <textarea
        :value="draft.rationale"
        class="inp"
        @input="emit('update', { rationale: ($event.target as HTMLTextAreaElement).value })"
      />
    </label>
    <fieldset>
      <legend>purpose</legend>
      <div class="check-group">
        <label
          v-for="value in VALID_PURPOSES"
          :key="value"
          class="check"
        >
          <input
            type="checkbox"
            :checked="draft.purpose.includes(value)"
            @change="togglePurpose(value)"
          > {{ value }}
        </label>
      </div>
    </fieldset>
    <fieldset>
      <legend>content</legend>
      <div class="check-group">
        <label
          v-for="value in VALID_CONTENTS"
          :key="value"
          class="check"
        >
          <input
            type="checkbox"
            :checked="draft.content.includes(value)"
            @change="toggleContent(value)"
          > {{ value }}
        </label>
      </div>
    </fieldset>
    <label class="field">
      stakeholders (comma-separated)
      <input
        class="inp"
        :value="listToCsv(draft.stakeholders)"
        @change="emit('update', { stakeholders: csvToList(($event.target as HTMLInputElement).value) })"
      >
    </label>
    <label class="field">
      concerns (comma-separated)
      <input
        class="inp"
        :value="listToCsv(draft.concerns)"
        @change="emit('update', { concerns: csvToList(($event.target as HTMLInputElement).value) })"
      >
    </label>
  </div>
</template>

<style scoped>
.field { display: block; margin: 8px 0; font-size: 12.5px; font-weight: 600; color: #6b7280; }
.inp { display: block; width: 100%; padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; font-family: inherit; box-sizing: border-box; margin-top: 3px; }
fieldset { border: 1px solid #d1d5db; border-radius: 8px; margin: 10px 0; padding: 8px 12px; }
legend { font-size: 12.5px; font-weight: 600; color: #6b7280; padding: 0 4px; }
.check-group { display: flex; flex-wrap: wrap; gap: 8px 18px; padding: 4px 2px; }
.check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #374151; font-weight: 500; cursor: pointer; }
.check input { margin: 0; cursor: pointer; }
</style>
