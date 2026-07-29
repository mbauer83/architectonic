<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { CONSTRAINT_DISPOSITIONS } from '../lib/constraintDispositions'
import { UCA_GUIDEWORD_SLUGS } from '../lib/ucaGuidewords'
import {
  showConcernClass as _showConcernClass,
  showDisposition as _showDisposition,
  showUcaType as _showUcaType,
  showBindingStatus as _showBindingStatus,
  showNodeRole as _showNodeRole,
  showSafeguardWarning as _showSafeguardWarning,
  canSubmit as _canSubmit,
} from './AssuranceNodeForm.helpers'
export type { AssuranceNodeFormData } from './AssuranceNodeForm.helpers'
import type { AssuranceNodeFormData } from './AssuranceNodeForm.helpers'

const props = withDefaults(defineProps<{
  initialData?: Partial<AssuranceNodeFormData>
  /** When set, locks the node_type (edit mode). */
  lockedNodeType?: string
  loading?: boolean
}>(), {
  initialData: undefined,
  lockedNodeType: undefined,
  loading: false,
})

const emit = defineEmits<{
  submit: [data: AssuranceNodeFormData]
  cancel: []
}>()

const ALL_NODE_TYPES = [
  'loss', 'hazard', 'control-structure-node', 'control-action',
  'unsafe-control-action', 'loss-scenario', 'assurance-constraint',
  'risk', 'incident', 'corrective-action', 'obligation',
] as const

const STATUSES = ['draft', 'active', 'accepted', 'archived']
const TLP_VALUES = ['TLP:WHITE', 'TLP:GREEN', 'TLP:AMBER', 'TLP:RED']
const CONCERN_CLASSES = ['safety', 'security', 'privacy', 'financial', 'operational', 'environmental']
const UCA_TYPES = UCA_GUIDEWORD_SLUGS
const BINDING_STATUSES = ['unbound-pending', 'bound', 'unresolved']
const NODE_ROLES = ['controller', 'controlled-process', 'actuator', 'sensor', 'feedback-channel', 'control-action-channel']

function defaultForm(): AssuranceNodeFormData {
  return {
    node_type: props.lockedNodeType ?? 'loss',
    name: '',
    status: 'draft',
    tlp: 'TLP:WHITE',
    concern_class: '',
    disposition: '',
    uca_type: '',
    binding_status: '',
    node_role: '',
    content_text: '',
  }
}

const form = ref<AssuranceNodeFormData>({ ...defaultForm(), ...props.initialData })

watch(() => props.initialData, (d) => {
  if (d) Object.assign(form.value, d)
}, { deep: true })

// Reset type-specific fields when the node type changes
watch(() => form.value.node_type, () => {
  form.value.concern_class = ''
  form.value.disposition = ''
  form.value.uca_type = ''
  form.value.binding_status = ''
  form.value.node_role = ''
})

// Which optional fields apply for each type
const showConcernClass = computed(() => _showConcernClass(form.value.node_type))
const showDisposition = computed(() => _showDisposition(form.value.node_type))
const showUcaType = computed(() => _showUcaType(form.value.node_type))
const showBindingStatus = computed(() => _showBindingStatus(form.value.node_type))
const showNodeRole = computed(() => _showNodeRole(form.value.node_type))

// Safety-disposition safeguard warning
const showSafeguardWarning = computed(() =>
  _showSafeguardWarning(form.value.node_type, form.value.disposition, form.value.concern_class)
)

const canSubmit = computed(() => _canSubmit(form.value.node_type, form.value.name, props.loading))

function handleSubmit() {
  if (!canSubmit.value) return
  emit('submit', { ...form.value })
}
</script>

<template>
  <form
    class="node-form"
    @submit.prevent="handleSubmit"
  >
    <!-- Type -->
    <div class="form-row">
      <label class="form-label">Type</label>
      <select
        v-if="!lockedNodeType"
        v-model="form.node_type"
        class="form-control"
        required
      >
        <option
          v-for="t in ALL_NODE_TYPES"
          :key="t"
          :value="t"
        >
          {{ t }}
        </option>
      </select>
      <span
        v-else
        class="form-locked-value"
      >{{ lockedNodeType }}</span>
    </div>

    <!-- Name -->
    <div class="form-row">
      <label class="form-label">Name <span class="required">*</span></label>
      <input
        v-model="form.name"
        type="text"
        class="form-control"
        placeholder="Short descriptive name"
        required
      >
    </div>

    <!-- Status + TLP (side by side) -->
    <div class="form-row form-row--split">
      <div>
        <label class="form-label">Status</label>
        <select
          v-model="form.status"
          class="form-control"
        >
          <option
            v-for="s in STATUSES"
            :key="s"
            :value="s"
          >
            {{ s }}
          </option>
        </select>
      </div>
      <div>
        <label class="form-label">TLP</label>
        <select
          v-model="form.tlp"
          class="form-control"
        >
          <option
            v-for="t in TLP_VALUES"
            :key="t"
            :value="t"
          >
            {{ t }}
          </option>
        </select>
      </div>
    </div>

    <!-- Concern class (type-specific) -->
    <div
      v-if="showConcernClass"
      class="form-row"
    >
      <label class="form-label">Concern class</label>
      <select
        v-model="form.concern_class"
        class="form-control"
      >
        <option value="">
          — none —
        </option>
        <option
          v-for="c in CONCERN_CLASSES"
          :key="c"
          :value="c"
        >
          {{ c }}
        </option>
      </select>
    </div>

    <!-- Disposition (assurance-constraint) -->
    <div
      v-if="showDisposition"
      class="form-row"
    >
      <label class="form-label">Disposition</label>
      <select
        v-model="form.disposition"
        class="form-control"
      >
        <option value="">
          — none —
        </option>
        <option
          v-for="d in CONSTRAINT_DISPOSITIONS"
          :key="d.slug"
          :value="d.slug"
        >
          {{ d.label }}
        </option>
      </select>
      <!-- Safety-subordination safeguard -->
      <p
        v-if="showSafeguardWarning"
        class="safeguard-warning"
        role="alert"
      >
        The safety-subordination safeguard (E503) rejects
        <strong>accepted</strong> on safety/security constraints.
        Use <em>eliminated</em>, <em>prevented-by-design</em>,
        <em>controlled-with-evidence</em>, or <em>alarp-justified</em>.
        This will be flagged as an error in verification.
      </p>
    </div>

    <!-- UCA type (unsafe-control-action) -->
    <div
      v-if="showUcaType"
      class="form-row"
    >
      <label class="form-label">UCA type</label>
      <select
        v-model="form.uca_type"
        class="form-control"
      >
        <option value="">
          — none —
        </option>
        <option
          v-for="u in UCA_TYPES"
          :key="u"
          :value="u"
        >
          {{ u }}
        </option>
      </select>
    </div>

    <!-- Binding status (control-structure-node) -->
    <div
      v-if="showBindingStatus"
      class="form-row"
    >
      <label class="form-label">Binding status</label>
      <select
        v-model="form.binding_status"
        class="form-control"
      >
        <option value="">
          — none —
        </option>
        <option
          v-for="b in BINDING_STATUSES"
          :key="b"
          :value="b"
        >
          {{ b }}
        </option>
      </select>
    </div>

    <!-- Node role (control-structure-node) -->
    <div
      v-if="showNodeRole"
      class="form-row"
    >
      <label class="form-label">Node role</label>
      <select
        v-model="form.node_role"
        class="form-control"
      >
        <option value="">
          — none —
        </option>
        <option
          v-for="r in NODE_ROLES"
          :key="r"
          :value="r"
        >
          {{ r }}
        </option>
      </select>
    </div>

    <!-- Content / notes -->
    <div class="form-row">
      <label class="form-label">Content / notes</label>
      <textarea
        v-model="form.content_text"
        class="form-control form-textarea"
        rows="3"
        placeholder="Free-form notes, evidence references, or context"
      />
    </div>

    <!-- Actions -->
    <div class="form-actions">
      <button
        type="submit"
        class="btn-primary"
        :disabled="!canSubmit"
      >
        {{ loading ? 'Saving…' : 'Save' }}
      </button>
      <button
        type="button"
        class="btn-secondary"
        @click="emit('cancel')"
      >
        Cancel
      </button>
    </div>
  </form>
</template>

<style scoped>
.node-form { display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row--split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-label { font-size: 12px; font-weight: 600; color: #374151; }
.required { color: #dc2626; }
.form-control {
  font-size: 13px;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #111827;
  width: 100%;
  box-sizing: border-box;
}
.form-control:focus { outline: 2px solid #2563eb; border-color: transparent; }
.form-textarea { resize: vertical; min-height: 64px; font-family: inherit; }
.form-locked-value { font-size: 13px; color: #6b7280; font-style: italic; }
.safeguard-warning {
  margin: 6px 0 0;
  padding: 8px 10px;
  background: #fef2f2;
  border: 1px solid #fca5a5;
  border-radius: 6px;
  font-size: 12px;
  color: #991b1b;
  line-height: 1.5;
}
.form-actions { display: flex; gap: 10px; padding-top: 4px; }
.btn-primary {
  padding: 7px 18px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-primary:disabled { opacity: 0.5; cursor: default; }
.btn-secondary {
  padding: 7px 18px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.btn-secondary:hover { background: #e5e7eb; }
</style>
