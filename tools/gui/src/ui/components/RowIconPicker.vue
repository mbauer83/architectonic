<script setup lang="ts">
/** The picker opened from a row: it states the choice for that row's instance, or for its type. */
import { inject } from 'vue'
import IconPicker from './IconPicker.vue'
import { diagramIconsKey } from '../composables/useDiagramIcons'
import type { IconScope, IconStatement, IconUploadForDiagram } from '../lib/diagramIcons'
import type { IconStyle } from '../../domain/schemas/icons'

const props = defineProps<{
  instanceId: string
  /** Asked of the library, so it offers only what applies: an entity id, or a type name. */
  applicableTo: string
  elementName: string
  typeName: string
}>()
const emit = defineEmits<{ done: [] }>()

const icons = inject(diagramIconsKey)!
const choose = (scope: IconScope, statement: IconStatement | null): void => {
  icons.choose(props.instanceId, props.typeName, scope, statement)
  emit('done')
}
const upload = (scope: IconScope, file: IconUploadForDiagram, style: IconStyle | undefined): void => {
  icons.upload(props.instanceId, props.typeName, scope, file, style)
  emit('done')
}
</script>

<template>
  <IconPicker
    :element-name="elementName"
    :type-name="typeName"
    :applicable-to="applicableTo"
    :styles="icons.styles.value"
    :current="icons.statedAt(instanceId, typeName)"
    @choose="choose"
    @upload="upload"
    @close="emit('done')"
  />
</template>
