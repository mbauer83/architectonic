<script setup lang="ts">
import { ref } from 'vue'
import type { Classifier } from './useDatatypeModel'
import StringListEditor from './StringListEditor.vue'

const props = defineProps<{
  classifier: Classifier
  roleRequired: boolean
}>()
const emit = defineEmits<{ update: [patch: Partial<Classifier>] }>()

const expanded = ref(false)
const roleMissing = () => props.roleRequired && !(props.classifier.role ?? '').trim()
</script>

<template>
  <section class="meta">
    <div class="meta-hdr">
      <span class="meta-title">Metadata</span>
      <button
        class="meta-toggle"
        type="button"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'Hide' : 'Show' }}
      </button>
    </div>

    <label class="role-row">
      <span class="role-label">
        Role<span
          v-if="roleRequired"
          class="req"
          title="Required for classifiers with attributes and sum-type general ends"
        >*</span>
      </span>
      <input
        class="role-in"
        :class="{ invalid: roleMissing() }"
        type="text"
        :value="classifier.role ?? ''"
        placeholder="Role of this data type in the system"
        @input="emit('update', { role: ($event.target as HTMLInputElement).value || undefined })"
      >
    </label>

    <template v-if="expanded">
      <StringListEditor
        label="Internal consistency criteria"
        placeholder="How this type's own attributes must relate"
        add-label="+ Rule"
        :items="classifier.internal_consistency_criteria"
        @update="emit('update', { internal_consistency_criteria: $event })"
      />
      <StringListEditor
        label="External consistency criteria"
        placeholder="How this data must relate to other data"
        add-label="+ Rule"
        :items="classifier.external_consistency_criteria"
        @update="emit('update', { external_consistency_criteria: $event })"
      />
      <StringListEditor
        label="Tags"
        placeholder="tag"
        add-label="+ Tag"
        :items="classifier.tags"
        @update="emit('update', { tags: $event })"
      />
      <label class="prov-row">
        <span class="prov-label">Provenance</span>
        <input
          class="prov-in"
          type="text"
          :value="classifier.provenance ?? ''"
          placeholder="Where this data type / its definition comes from"
          @input="emit('update', { provenance: ($event.target as HTMLInputElement).value || undefined })"
        >
      </label>
    </template>
  </section>
</template>

<style scoped>
.meta { display: flex; flex-direction: column; gap: 5px; }
.meta-hdr { display: flex; align-items: center; justify-content: space-between; }
.meta-title { font-size: 11px; font-weight: 600; color: #374151; }
.meta-toggle { font-size: 10px; padding: 0 6px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; color: #6b7280; }
.role-row, .prov-row { display: flex; flex-direction: column; gap: 2px; }
.role-label, .prov-label { font-size: 10px; color: #6b7280; }
.req { color: #dc2626; margin-left: 1px; }
.role-in, .prov-in { font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 2px 4px; }
.role-in.invalid { border-color: #fca5a5; background: #fef2f2; }
</style>
