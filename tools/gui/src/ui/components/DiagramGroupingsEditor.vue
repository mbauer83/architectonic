<script setup lang="ts">
/**
 * Author the labelled boxes a diagram draws.
 *
 * The panel asks for two things only — a label, and which of the entities already selected for this
 * diagram go in the box. It never asks how the box should look: the backend derives that from the
 * members (one domain gives that domain's look, several give the dashed ArchiMate grouping look), so
 * offering a picker here would be offering a way to contradict the members.
 *
 * A member already placed in another box is disabled rather than hidden, because "already in
 * *Forces*" is the answer to the question the author is asking when they cannot find it.
 */
import { computed } from 'vue'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import { claimedMemberIds } from '../../domain/authoredGrouping'

const props = defineProps<{
  /** The current boxes, outermost first. */
  modelValue: readonly AuthoredGrouping[]
  /** The entities available to place — those the diagram already draws. */
  candidates: readonly { id: string; label: string }[]
}>()

const emit = defineEmits<{ 'update:modelValue': [readonly AuthoredGrouping[]] }>()

const labelById = computed(() => new Map(props.candidates.map((c) => [c.id, c.label])))
const claimed = computed(() => claimedMemberIds(props.modelValue))

const holderOf = (id: string): string | null => {
  for (const group of props.modelValue) {
    if (group['entity-ids'].includes(id)) return group.label || '(unnamed)'
  }
  return null
}

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

const toggleMember = (index: number, id: string): void => {
  const group = props.modelValue[index]
  const members = group['entity-ids']
  replace(index, {
    ...group,
    'entity-ids': members.includes(id) ? members.filter((m) => m !== id) : [...members, id],
  })
}

const isDisabled = (index: number, id: string): boolean =>
  claimed.value.has(id) && !props.modelValue[index]['entity-ids'].includes(id)
</script>

<template>
  <section class="groupings">
    <header class="groupings__head">
      <h3>Groupings</h3>
      <button
        type="button"
        class="groupings__add"
        @click="addGroup"
      >
        Add box
      </button>
    </header>
    <p
      v-if="modelValue.length === 0"
      class="groupings__empty"
    >
      No boxes. A box gives a set of elements a label the model does not carry — its look follows
      from what you put in it.
    </p>
    <ol
      v-else
      class="groupings__list"
    >
      <li
        v-for="(group, index) in modelValue"
        :key="index"
        class="groupings__item"
      >
        <div class="groupings__row">
          <input
            class="groupings__label"
            :value="group.label"
            placeholder="Box label"
            :aria-label="`Label for box ${index + 1}`"
            @input="setLabel(index, ($event.target as HTMLInputElement).value)"
          >
          <button
            type="button"
            class="groupings__remove"
            @click="removeGroup(index)"
          >
            Remove
          </button>
        </div>
        <ul class="groupings__members">
          <li
            v-for="candidate in candidates"
            :key="candidate.id"
          >
            <label :class="{ 'is-taken': isDisabled(index, candidate.id) }">
              <input
                type="checkbox"
                :checked="group['entity-ids'].includes(candidate.id)"
                :disabled="isDisabled(index, candidate.id)"
                @change="toggleMember(index, candidate.id)"
              >
              <span>{{ labelById.get(candidate.id) ?? candidate.id }}</span>
              <em v-if="isDisabled(index, candidate.id)">in “{{ holderOf(candidate.id) }}”</em>
            </label>
          </li>
        </ul>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.groupings { margin-block: 1rem; }
.groupings__head { display: flex; align-items: center; justify-content: space-between; }
.groupings__head h3 { margin: 0; font-size: 0.95rem; }
.groupings__empty { color: var(--muted, #666); font-size: 0.85rem; margin: 0.4rem 0 0; }
.groupings__list { list-style: none; margin: 0.5rem 0 0; padding: 0; }
.groupings__item { border: 1px solid var(--border, #ddd); border-radius: 4px; padding: 0.5rem; margin-bottom: 0.5rem; }
.groupings__row { display: flex; gap: 0.5rem; }
.groupings__label { flex: 1; }
.groupings__members {
  list-style: none; margin: 0.5rem 0 0; padding: 0;
  display: flex; flex-wrap: wrap; gap: 0.25rem 1rem;
}
.groupings__members label { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.85rem; }
.groupings__members .is-taken { opacity: 0.55; }
.groupings__members em { color: var(--muted, #666); font-style: normal; font-size: 0.78rem; }
</style>
