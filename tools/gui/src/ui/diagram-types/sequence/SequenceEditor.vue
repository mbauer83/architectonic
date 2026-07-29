<script setup lang="ts">
import { computed } from 'vue'
import type { DiagramTypeUiConfig, EntityDisplayInfo } from '../../../domain'
import { useSequenceModel } from './useSequenceModel'
import LifelineStrip from './LifelineStrip.vue'
import MessageList from './MessageList.vue'
import GroupingEditor from './GroupingEditor.vue'
import NotesPanel from './NotesPanel.vue'

const props = defineProps<{
  uiConfig: DiagramTypeUiConfig
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
}>()
const emit = defineEmits<{ diagramEntitiesChange: [patch: Record<string, unknown>] }>()

const model = useSequenceModel(() => props.diagramEntities, (p) => emit('diagramEntitiesChange', p))

const showGroupings = computed(() => model.groupings.value.length > 0)
const showNotes = computed(() => model.notes.value.length > 0)
const canAddGrouping = computed(() => model.messages.value.length >= 2)
const canAddNote = computed(() => model.lifelines.value.length > 0)
</script>

<template>
  <section class="seq-editor">
    <LifelineStrip
      :lifelines="model.lifelines.value"
      :entities="entities"
      @add="model.addLifeline()"
      @remove="model.removeLifeline($event)"
      @update="model.updateLifeline($event.id, $event.patch)"
      @reorder="model.reorderLifelines($event)"
    />

    <MessageList
      :messages="model.messages.value"
      :lifelines="model.lifelines.value"
      :from-map="model.fromMap.value"
      :to-map="model.toMap.value"
      @add="model.addMessage()"
      @remove="model.removeMessage($event)"
      @update="model.updateMessage($event.id, $event.patch)"
      @set-from="model.setMessageFrom($event.msgId, $event.lifelineId)"
      @set-to="model.setMessageTo($event.msgId, $event.lifelineId)"
      @reorder="model.reorderMessages($event)"
    />

    <GroupingEditor
      v-if="showGroupings"
      :groupings="model.groupings.value"
      :messages="model.messages.value"
      @add="model.addGrouping()"
      @remove="model.removeGrouping($event)"
      @update="model.updateGrouping($event.id, $event.patch)"
    />

    <NotesPanel
      v-if="showNotes"
      :notes="model.notes.value"
      :lifelines="model.lifelines.value"
      :messages="model.messages.value"
      @add="model.addNote()"
      @remove="model.removeNote($event)"
      @update="model.updateNote($event.id, $event.patch)"
    />

    <div class="seq-optional">
      <button
        v-if="!showGroupings"
        class="opt-btn"
        type="button"
        :disabled="!canAddGrouping"
        :title="!canAddGrouping ? 'Add at least 2 messages first' : ''"
        @click="model.addGrouping()"
      >
        + Grouping
      </button>
      <button
        v-if="!showNotes"
        class="opt-btn"
        type="button"
        :disabled="!canAddNote"
        :title="!canAddNote ? 'Add lifelines first' : ''"
        @click="model.addNote()"
      >
        + Note
      </button>
    </div>
  </section>
</template>

<style scoped>
.seq-editor { display: flex; flex-direction: column; gap: 14px; }
.seq-optional { display: flex; gap: 8px; flex-wrap: wrap; padding-top: 2px; }
.opt-btn {
  font-size: 12px; color: #6b7280; background: none; border: 1px dashed #cbd5e1;
  border-radius: 5px; padding: 4px 10px; cursor: pointer;
}
.opt-btn:hover:not(:disabled) { color: #2563eb; border-color: #93c5fd; background: #eff6ff; }
.opt-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
