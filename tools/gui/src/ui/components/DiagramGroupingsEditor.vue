<script setup lang="ts">
/**
 * Author the labelled boxes a diagram draws.
 *
 * A box is created empty and filled afterwards, because that is the order the thought arrives in:
 * you know a diagram needs a "Forces" box before you know everything that goes in it. Each box
 * carries its own entity input, so adding a member is one action against the box you mean rather
 * than a list of every candidate repeated per box.
 *
 * Picking an entity that the diagram does not yet draw adds it to the diagram as well — a member the
 * diagram does not draw is one the renderer silently ignores, so offering the choice would be
 * offering a way to get nothing.
 *
 * The panel never asks how a box should look: the backend derives that from the members — one domain
 * gives that domain's look, several give the dashed ArchiMate grouping look — so a picker here would
 * be a way to contradict the members.
 */
import { computed } from 'vue'
import EntityPickerInput from './EntityPickerInput.vue'
import type { EntityDisplayInfo } from '../../domain/schemas/entities'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import { claimedMemberIds } from '../../domain/authoredGrouping'

const props = defineProps<{
  /** The current boxes, outermost first. */
  modelValue: readonly AuthoredGrouping[]
  /** The entities the diagram draws, for resolving a member id to a name. */
  candidates: readonly { id: string; label: string }[]
  diagramType?: string
  viewpoint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [readonly AuthoredGrouping[]]
  /** A picked entity the diagram does not draw yet; the view adds it. */
  'add-entity': [EntityDisplayInfo]
}>()

const labelById = computed(() => new Map(props.candidates.map((c) => [c.id, c.label])))
/** Claimed anywhere, so the picker cannot offer a member already placed in another box. */
const claimed = computed(() => new Set(claimedMemberIds(props.modelValue)))

const replace = (index: number, group: AuthoredGrouping): void => {
  emit('update:modelValue', props.modelValue.map((g, i) => (i === index ? group : g)))
}

const addGroup = (): void => {
  emit('update:modelValue', [...props.modelValue, { label: '', 'entity-ids': [] }])
}

const removeGroup = (index: number): void => {
  emit('update:modelValue', props.modelValue.filter((_g, i) => i !== index))
}

const setLabel = (index: number, label: string): void => {
  replace(index, { ...props.modelValue[index], label })
}

const addMember = (index: number, entity: EntityDisplayInfo): void => {
  if (!labelById.value.has(entity.artifact_id)) emit('add-entity', entity)
  const group = props.modelValue[index]
  if (group['entity-ids'].includes(entity.artifact_id)) return
  replace(index, { ...group, 'entity-ids': [...group['entity-ids'], entity.artifact_id] })
}

const removeMember = (index: number, id: string): void => {
  const group = props.modelValue[index]
  replace(index, { ...group, 'entity-ids': group['entity-ids'].filter((m) => m !== id) })
}
</script>

<template>
  <section class="grp">
    <div class="grp__head">
      <span class="lbl">Groupings</span>
      <button
        type="button"
        class="grp__add"
        @click="addGroup"
      >
        + Add grouping
      </button>
    </div>

    <p
      v-if="modelValue.length === 0"
      class="grp__empty"
    >
      A grouping draws a labelled box around some of the entities. Its look follows from what you put
      in it.
    </p>

    <div
      v-for="(group, index) in modelValue"
      :key="index"
      class="grp__box"
    >
      <div class="grp__row">
        <input
          class="grp__label"
          :value="group.label"
          placeholder="Grouping label"
          :aria-label="`Label for grouping ${index + 1}`"
          @input="setLabel(index, ($event.target as HTMLInputElement).value)"
        >
        <button
          type="button"
          class="grp__remove"
          :aria-label="`Remove grouping ${index + 1}`"
          @click="removeGroup(index)"
        >
          ×
        </button>
      </div>

      <EntityPickerInput
        :excluded-ids="claimed"
        :diagram-type="diagramType"
        :viewpoint="viewpoint"
        placeholder="Add entities to this grouping…"
        @select="addMember(index, $event)"
      />

      <ul
        v-if="group['entity-ids'].length"
        class="grp__members"
      >
        <li
          v-for="id in group['entity-ids']"
          :key="id"
          class="grp__member"
        >
          <span class="grp__name">{{ labelById.get(id) ?? id }}</span>
          <button
            type="button"
            class="grp__drop"
            :aria-label="`Remove ${labelById.get(id) ?? id} from this grouping`"
            @click="removeMember(index, id)"
          >
            ×
          </button>
        </li>
      </ul>
      <p
        v-else
        class="grp__hint"
      >
        No entities yet — add them above.
      </p>
    </div>
  </section>
</template>

<style scoped>
.grp__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.lbl {
  display: block; font-size: 11px; font-weight: 700; color: #374151;
  text-transform: uppercase; letter-spacing: .05em;
}
.grp__add {
  padding: 5px 12px; background: #f3f4f6; color: #1d4ed8; border: 1px solid #bfdbfe;
  border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer;
}
.grp__add:hover { background: #eff6ff; }
.grp__empty, .grp__hint { font-size: 12px; color: #9ca3af; margin: 0; }
.grp__box {
  border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px;
  margin-top: 8px; background: #fafafa;
}
.grp__row { display: flex; gap: 6px; margin-bottom: 8px; }
.grp__label {
  flex: 1; padding: 6px 8px; border: 1px solid #d1d5db;
  border-radius: 6px; font-size: 13px;
}
.grp__remove, .grp__drop {
  background: none; border: none; color: #9ca3af; cursor: pointer;
  font-size: 16px; line-height: 1; padding: 0 6px;
}
.grp__remove:hover, .grp__drop:hover { color: #b91c1c; }
.grp__members { list-style: none; margin: 8px 0 0; padding: 0; }
.grp__member {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
  padding: 4px 6px; background: white; border: 1px solid #e5e7eb;
  border-radius: 4px; margin-bottom: 4px;
}
.grp__name { font-size: 12px; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
