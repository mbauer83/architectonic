<script setup lang="ts">
/**
 * Where a model entity is filed, chosen from the model-project collections.
 *
 * A named wrapper per axis rather than an `axis` prop at every call site: the four collection axes
 * are independent registries, so which one files which kind is a fact about the kind — stated here
 * once instead of repeated on six forms, each free to name the wrong one.
 */
import ArtifactHomeSelect from './ArtifactHomeSelect.vue'

const model = defineModel<string>({ required: true })
</script>

<template>
  <ArtifactHomeSelect
    v-model="model"
    axis="model-project"
  />
</template>
