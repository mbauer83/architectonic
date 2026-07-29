<script setup lang="ts">
import { computed } from 'vue'
import type { PromotionGroupMappingEntry, PromotionPlan, StructuralClosureRequirement } from '../../domain'
import type { ConflictStrategy } from '../composables/promotionShared'

const props = defineProps<{
  loading: boolean
  errorMessage: string
  plan: PromotionPlan | null
  strategies: Record<string, ConflictStrategy>
  unresolvedCount: number
  groupMappingResolutions: Record<string, string>
  unresolvedGroupConflictCount: number
}>()

const emit = defineEmits<{
  setStrategy: [artifactId: string, strategy: ConflictStrategy]
  setGroupMapping: [engagementSlug: string, enterpriseSlug: string]
  includeClosure: [requirement: StructuralClosureRequirement]
}>()

/** The structured closure panel below renders these facts actionably, so the raw prose
 * duplicates are filtered out of the plain error box. */
const visibleSchemaErrors = computed(() =>
  (props.plan?.schema_errors ?? []).filter((error) => !error.startsWith('Broken structural closure:')))

const strategyOptions = [
  { value: 'accept_enterprise', label: 'Keep enterprise version' },
  { value: 'accept_engagement', label: 'Replace with selected version' },
] as const

const updateStrategy = (artifactId: string, event: Event) => {
  emit('setStrategy', artifactId, (event.target as HTMLInputElement).value as ConflictStrategy)
}

const matchStatusLabel = (entry: PromotionGroupMappingEntry): string => {
  if (entry.match_status === 'matched_by_id') return '✓ Matched'
  if (entry.match_status === 'conflict') return '⚠ Conflict'
  return '+ New'
}
</script>

<template>
  <div class="card step-card">
    <h2 class="card-title">
      Plan Summary
    </h2>

    <div
      v-if="loading"
      class="state-msg"
    >
      Refreshing plan…
    </div>
    <p
      v-if="errorMessage"
      class="error-msg"
    >
      {{ errorMessage }}
    </p>

    <template v-if="props.plan">
      <div
        v-if="props.plan.warnings.length"
        class="warnings-box"
      >
        <div
          v-for="warning in props.plan.warnings"
          :key="warning"
          class="warn-item"
        >
          {{ warning }}
        </div>
      </div>

      <div
        v-if="visibleSchemaErrors.length"
        class="errors-box"
      >
        <div
          v-for="error in visibleSchemaErrors"
          :key="error"
          class="error-item"
        >
          {{ error }}
        </div>
      </div>

      <div
        v-if="props.plan.structural_closure.length"
        class="closure-box"
      >
        <div
          v-for="requirement in props.plan.structural_closure"
          :key="requirement.entity_id"
          class="closure-item"
        >
          <p class="closure-head">
            <template v-if="requirement.kind === 'junction'">
              Junction <b>{{ requirement.entity_name }}</b> has no meaning without its complete
              connection set — {{ requirement.missing.length }} connected
              {{ requirement.missing.length === 1 ? 'entity is' : 'entities are' }} missing from the selection:
            </template>
            <template v-else>
              Grouping <b>{{ requirement.entity_name }}</b> would be promoted without its contents,
              erasing the membership edges — {{ requirement.missing.length }}
              member{{ requirement.missing.length === 1 ? ' is' : 's are' }} missing from the selection:
            </template>
          </p>
          <ul class="closure-missing">
            <li
              v-for="entity in requirement.missing"
              :key="entity.artifact_id"
            >
              <span class="closure-name">{{ entity.name }}</span>
              <span class="closure-type mono">{{ entity.artifact_type }}</span>
            </li>
          </ul>
          <button
            class="btn btn--closure"
            type="button"
            :disabled="loading"
            @click="emit('includeClosure', requirement)"
          >
            + Include {{ requirement.missing.length === 1 ? 'it' : `all ${requirement.missing.length}` }} in the promotion
          </button>
        </div>
      </div>

      <section
        v-if="props.plan.already_in_enterprise.length"
        class="section"
      >
        <h3 class="section-title">
          Already in the enterprise repository
        </h3>
        <ul class="id-list id-list--muted">
          <li
            v-for="artifactId in props.plan.already_in_enterprise"
            :key="artifactId"
            class="mono"
          >
            {{ artifactId }}
          </li>
        </ul>
      </section>

      <section
        v-for="entry in [
          { title: 'New entities to promote', items: props.plan.entities_to_add },
          { title: 'New documents to promote', items: props.plan.documents_to_add },
          { title: 'New diagrams to promote', items: props.plan.diagrams_to_add },
          { title: 'Selected connections', items: props.plan.connection_ids },
        ]"
        v-show="entry.items.length"
        :key="entry.title"
        class="section"
      >
        <h3 class="section-title">
          {{ entry.title }}
        </h3>
        <ul class="id-list">
          <li
            v-for="artifactId in entry.items"
            :key="artifactId"
            class="mono"
          >
            {{ artifactId }}
          </li>
        </ul>
      </section>

      <section
        v-for="group in [
          {
            title: 'Entity conflicts',
            conflicts: props.plan.conflicts.map((conflict) => ({
              id: conflict.engagement_id,
              heading: `${conflict.engagement_id} vs enterprise ${conflict.enterprise_id}`,
              meta: '',
            })),
          },
          {
            title: 'Document conflicts',
            conflicts: props.plan.doc_conflicts.map((conflict) => ({
              id: conflict.engagement_id,
              heading: `${conflict.engagement_title} vs enterprise ${conflict.enterprise_title}`,
              meta: `${conflict.engagement_id} → ${conflict.enterprise_id}`,
            })),
          },
          {
            title: 'Diagram conflicts',
            conflicts: props.plan.diagram_conflicts.map((conflict) => ({
              id: conflict.engagement_id,
              heading: `${conflict.engagement_name} vs enterprise ${conflict.enterprise_name}`,
              meta: `${conflict.engagement_id} → ${conflict.enterprise_id}`,
            })),
          },
        ]"
        v-show="group.conflicts.length"
        :key="group.title"
        class="section"
      >
        <h3 class="section-title section-title--warn">
          {{ group.title }}
        </h3>
        <div
          v-for="conflict in group.conflicts"
          :key="conflict.id"
          class="conflict-card"
        >
          <div class="conflict-header">
            {{ conflict.heading }}
          </div>
          <div
            v-if="conflict.meta"
            class="conflict-meta mono"
          >
            {{ conflict.meta }}
          </div>
          <div class="conflict-strategies">
            <label
              v-for="option in strategyOptions"
              :key="option.value"
              class="strategy-opt"
            >
              <input
                :checked="props.strategies[conflict.id] === option.value"
                type="radio"
                :name="`conflict-${conflict.id}`"
                :value="option.value"
                @change="updateStrategy(conflict.id, $event)"
              >
              {{ option.label }}
            </label>
          </div>
        </div>
      </section>

      <div
        v-if="props.unresolvedCount"
        class="warn-banner"
      >
        {{ props.unresolvedCount }} conflict{{ props.unresolvedCount > 1 ? 's' : '' }}
        still need{{ props.unresolvedCount === 1 ? 's' : '' }} a resolution strategy.
      </div>

      <section
        v-if="(props.plan?.group_mapping ?? []).length"
        class="section"
      >
        <h3 class="section-title">
          Model-Project Mapping
        </h3>
        <p class="group-map-hint">
          Each engagement model-project will be mapped to an enterprise group.
        </p>
        <div
          v-for="entry in props.plan?.group_mapping ?? []"
          :key="entry.engagement_slug"
          class="group-map-row"
          :class="`group-map-row--${entry.match_status}`"
        >
          <span class="group-map-badge">{{ matchStatusLabel(entry) }}</span>
          <span class="group-map-eng mono">{{ entry.engagement_slug }}</span>
          <span class="group-map-arrow">→</span>
          <span
            v-if="entry.match_status === 'matched_by_id'"
            class="group-map-ent mono"
          >{{ entry.enterprise_slug }}</span>
          <select
            v-else
            class="group-map-sel"
            :value="props.groupMappingResolutions[entry.engagement_slug] ?? entry.enterprise_slug"
            @change="emit('setGroupMapping', entry.engagement_slug, ($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="g in (props.plan?.available_enterprise_groups ?? [])"
              :key="g.slug"
              :value="g.slug"
            >
              {{ g.name }} ({{ g.slug }})
            </option>
            <option :value="entry.engagement_slug">
              + Create new: {{ entry.engagement_slug }}
            </option>
          </select>
        </div>
      </section>

      <div
        v-if="props.unresolvedGroupConflictCount"
        class="warn-banner"
      >
        {{ props.unresolvedGroupConflictCount }} group conflict{{ props.unresolvedGroupConflictCount > 1 ? 's' : '' }}
        still need{{ props.unresolvedGroupConflictCount === 1 ? 's' : '' }} a mapping.
      </div>
    </template>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 20px 24px; margin-bottom: 16px; }
.card-title { font-size: 16px; font-weight: 600; color: #111827; margin-bottom: 10px; }
.section { margin-top: 18px; }
.section-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #374151; margin-bottom: 8px; }
.section-title--warn { color: #b45309; }
.warnings-box { background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }
.closure-box { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }
.closure-item { padding: 4px 0; }
.closure-item + .closure-item { border-top: 1px dashed #fed7aa; margin-top: 8px; padding-top: 10px; }
.closure-head { font-size: 12.5px; color: #9a3412; margin: 0 0 6px; }
.closure-missing { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.closure-missing li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: #431407; }
.closure-name { font-weight: 600; }
.closure-type { font-size: 11px; color: #9a3412; }
.btn--closure { background: #ea580c; color: #fff; border: none; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn--closure:hover:not(:disabled) { background: #c2410c; }
.btn--closure:disabled { opacity: .5; cursor: wait; }
.errors-box { background: #fff7f7; border: 1px solid #fecaca; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }
.warn-item { font-size: 13px; color: #92400e; }
.error-item { font-size: 13px; color: #b91c1c; }
.id-list { list-style: none; display: flex; flex-direction: column; gap: 3px; }
.id-list--muted .mono { color: #9ca3af; }
.conflict-card { border: 1px solid #fde68a; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; background: #fffbeb; }
.conflict-header { margin-bottom: 6px; color: #111827; }
.conflict-meta { font-size: 11px; color: #6b7280; margin-bottom: 8px; }
.conflict-strategies { display: flex; gap: 16px; flex-wrap: wrap; }
.strategy-opt { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.strategy-opt input[type=radio] { accent-color: #2563eb; }
.warn-banner {
  margin-top: 14px; padding: 10px 14px; background: #fef3c7; border: 1px solid #fde68a;
  border-radius: 6px; font-size: 13px; color: #92400e; font-weight: 500;
}
.state-msg { font-size: 13px; color: #6b7280; }
.error-msg { margin-top: 12px; color: #dc2626; font-size: 13px; white-space: pre-wrap; }
.mono { font-family: monospace; font-size: 12px; }
.group-map-hint { font-size: 12px; color: #6b7280; margin-bottom: 8px; }
.group-map-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 6px; margin-bottom: 4px; background: #f8fafc; border: 1px solid #e2e8f0; font-size: 13px; }
.group-map-row--conflict { background: #fffbeb; border-color: #fde68a; }
.group-map-badge { font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; white-space: nowrap; background: #e2e8f0; color: #334155; }
.group-map-row--matched_by_id .group-map-badge { background: #dcfce7; color: #166534; }
.group-map-row--conflict .group-map-badge { background: #fef3c7; color: #92400e; }
.group-map-row--new .group-map-badge { background: #dbeafe; color: #1e40af; }
.group-map-eng { flex: 0 0 auto; }
.group-map-arrow { color: #9ca3af; }
.group-map-ent { color: #374151; }
.group-map-sel { font-size: 12px; border: 1px solid #d1d5db; border-radius: 4px; padding: 2px 6px; background: white; cursor: pointer; flex: 1; min-width: 0; }
</style>
