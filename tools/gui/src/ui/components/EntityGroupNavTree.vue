<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGroupManagement, type GroupOption } from '../composables/useGroupManagement'
import {
  domainOptionsForModules,
  FRAMEWORK_GROUPS,
  frameworkGroupsForModules,
  getDomainLabel,
} from '../lib/domains'
import type { ModuleSummary } from '../../domain'

const props = defineProps<{
  groups: GroupOption[]
  activeGroup: string
  activeDomain: string
  manageable?: boolean
  axis?: string
  showArchived?: boolean
  domainCounts?: Record<string, number>
  modules?: readonly ModuleSummary[]
}>()

const emit = defineEmits<{
  'update:activeGroup': [slug: string]
  'update:activeDomain': [domain: string]
  'update:showArchived': [value: boolean]
  'group-mutated': []
  'navigate-to-groups': []
}>()

const mgmt = useGroupManagement({
  axis: props.axis ?? 'model-project',
  onMutated: () => emit('group-mutated'),
})

const expandedFramework = ref<string | null>(null)

const visibleGroups = computed(() =>
  props.groups.filter(g => props.showArchived || !g.archived),
)

const selectGroup = (slug: string) => {
  emit('update:activeGroup', slug)
  expandedFramework.value = null
}

const selectDomain = (domain: string) => emit('update:activeDomain', domain)

const toggleFramework = (key: string) => {
  expandedFramework.value = expandedFramework.value === key ? null : key
}

const activeGroupEntry = computed(() =>
  props.groups.find(g => g.slug === props.activeGroup) ?? null,
)

const restrictedDomains = computed((): string[] | null => {
  const mo = activeGroupEntry.value?.meta_ontology
  if (!mo) return null
  const fw = FRAMEWORK_GROUPS.find(f => f.key === mo)
  if (!fw || !frameworkGroups.value.some(group => group.key === mo)) return []
  return fw ? (fw.domains as readonly string[]).slice() : null
})

const domainOptionsForGroup = computed(() =>
  domainOptionsForModules(props.modules),
)

const isDomainVisible = (domainKey: string): boolean => {
  if (!restrictedDomains.value) return true
  return restrictedDomains.value.includes(domainKey)
}

const hasDomainEntities = (domainKey: string): boolean =>
  !props.domainCounts || (props.domainCounts[domainKey] ?? 0) > 0

const frameworkGroups = computed(() => frameworkGroupsForModules(props.modules))

const visibleDomains = (fw: (typeof FRAMEWORK_GROUPS)[number]): readonly string[] =>
  props.domainCounts
    ? (fw.domains as readonly string[]).filter(d => (props.domainCounts![d] ?? 0) > 0)
    : (fw.domains)
</script>

<template>
  <div class="tree">
    <!-- All projects → groups overview -->
    <button
      class="tree-btn tree-btn--project"
      :class="{ active: activeGroup === '' }"
      @click="emit('navigate-to-groups')"
    >
      All
    </button>

    <!-- Project nodes -->
    <div
      v-for="g in visibleGroups"
      :key="g.slug"
      class="project-node"
    >
      <div class="project-row">
        <button
          class="tree-btn tree-btn--project"
          :class="{ active: activeGroup === g.slug, archived: g.archived }"
          :title="g.archived ? `${g.name} (archived)` : g.name"
          @click="selectGroup(g.slug)"
        >
          <span class="node-label">{{ g.name }}</span>
          <span
            v-if="g.count !== undefined"
            class="node-count"
          >{{ g.count }}</span>
        </button>
        <button
          v-if="manageable"
          class="mgmt-btn"
          title="Manage"
          @click.stop="mgmt.openRename(g)"
        >
          ⋯
        </button>
      </div>

      <!-- Domain sub-tree — only under active project -->
      <div
        v-if="activeGroup === g.slug"
        class="domain-subtree"
      >
        <!-- Restricted: flat domain list (no framework level) -->
        <template v-if="restrictedDomains">
          <button
            v-for="d in domainOptionsForGroup.filter(d => isDomainVisible(d.key) && hasDomainEntities(d.key))"
            :key="d.key"
            class="tree-btn tree-btn--domain"
            :class="{ active: activeDomain === d.key }"
            @click="selectDomain(d.key)"
          >
            {{ d.label }}
          </button>
        </template>

        <!-- Unrestricted: framework → domain tree (only frameworks with entities; single-domain shown flat) -->
        <template v-else>
          <div
            v-for="fw in frameworkGroups"
            :key="fw.key"
            class="framework-node"
          >
            <!-- Single-domain framework: show domain button directly if it has entities -->
            <button
              v-if="fw.domains.length === 1 && hasDomainEntities(fw.domains[0] as string)"
              class="tree-btn tree-btn--domain"
              :class="{ active: activeDomain === fw.domains[0] }"
              @click="selectDomain(fw.domains[0] as string)"
            >
              {{ getDomainLabel(fw.domains[0] as string) }}
            </button>
            <!-- Multi-domain framework: expandable wrapper (only shown when any domain has entities) -->
            <template v-else-if="fw.domains.length > 1 && visibleDomains(fw).length > 0">
              <button
                class="tree-btn tree-btn--framework"
                :class="{ expanded: expandedFramework === fw.key }"
                @click="toggleFramework(fw.key)"
              >
                <span class="expand-icon">{{ expandedFramework === fw.key ? '▾' : '▸' }}</span>
                {{ fw.label }}
              </button>
              <div
                v-if="expandedFramework === fw.key"
                class="domain-list"
              >
                <button
                  v-for="domKey in visibleDomains(fw)"
                  :key="domKey"
                  class="tree-btn tree-btn--domain tree-btn--leaf"
                  :class="{ active: activeDomain === domKey }"
                  @click="selectDomain(domKey)"
                >
                  {{ getDomainLabel(domKey) }}
                </button>
              </div>
            </template>
          </div>
        </template>
      </div>
    </div>

    <!-- Management actions -->
    <div class="tree-actions">
      <button
        v-if="manageable"
        class="action-btn"
        @click="mgmt.openCreate()"
      >
        + New
      </button>
      <button
        class="action-btn"
        :class="{ active: showArchived }"
        @click="emit('update:showArchived', !showArchived)"
      >
        {{ showArchived ? '− archived' : '+ archived' }}
      </button>
    </div>

    <!-- Dialogs -->
    <div
      v-if="mgmt.dialog.value === 'create'"
      class="group-dialog"
    >
      <div class="dialog-title">
        New Project
      </div>
      <label class="field">Name<input
        v-model="mgmt.fieldName.value"
        class="field-input"
        @input="mgmt.fieldSlug.value = mgmt.slugify(mgmt.fieldName.value)"
      ></label>
      <label class="field">Slug<input
        v-model="mgmt.fieldSlug.value"
        class="field-input"
      ></label>
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--primary"
          :disabled="mgmt.busy.value || !mgmt.fieldSlug.value || !mgmt.fieldName.value"
          @click="mgmt.submitCreate()"
        >
          Create
        </button>
      </div>
    </div>

    <div
      v-if="mgmt.dialog.value === 'rename'"
      class="group-dialog"
    >
      <div class="dialog-title">
        Rename "{{ mgmt.dialogTarget.value?.name }}"
      </div>
      <label class="field">Display name<input
        v-model="mgmt.fieldName.value"
        class="field-input"
      ></label>
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--primary"
          :disabled="mgmt.busy.value || !mgmt.fieldName.value"
          @click="mgmt.submitRename()"
        >
          Rename
        </button>
      </div>
    </div>

    <div
      v-if="mgmt.dialog.value === 'archive'"
      class="group-dialog"
    >
      <div class="dialog-title">
        {{ mgmt.dialogTarget.value?.archived ? 'Unarchive' : 'Archive' }} "{{ mgmt.dialogTarget.value?.name }}"
      </div>
      <p
        v-if="mgmt.archiveNeedsConfirm.value"
        class="dialog-note"
      >
        Has {{ mgmt.dialogTarget.value?.count }} items. Type slug to confirm:
      </p>
      <input
        v-if="mgmt.archiveNeedsConfirm.value"
        v-model="mgmt.fieldConfirm.value"
        class="field-input"
        :placeholder="mgmt.dialogTarget.value?.slug"
      >
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--primary"
          :disabled="mgmt.busy.value || !mgmt.archiveReady.value"
          @click="mgmt.submitArchive()"
        >
          {{ mgmt.dialogTarget.value?.archived ? 'Unarchive' : 'Archive' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped src="./EntityGroupNavTree.css"></style>
