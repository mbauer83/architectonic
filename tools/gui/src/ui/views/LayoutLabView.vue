<script setup lang="ts">
/**
 * The layout lab: try moving and resizing the elements and boxes of a real diagram, watch the lines
 * re-route, see each rule a line breaks, and compare with the server's composed picture. A bench for
 * judging the layout implementation, not the canvas edit mode: nothing is saved, and its one gesture
 * decides nothing about the edit mode's.
 */
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { useRoute, useRouter } from 'vue-router'
import { layoutLabIsOn } from '../../adapters/http/HttpLayoutLab'
import type { DiagramSummary } from '../../domain'
import { modelServiceKey, toastKey } from '../keys'
import { layoutLabRoute } from '../router/artifactRoutes'
import { useLayoutLab } from '../composables/useLayoutLab'
import LayoutLabCanvas from '../components/layoutLab/LayoutLabCanvas.vue'

const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)
const route = useRoute()
const router = useRouter()
const lab = useLayoutLab()

const labIsOn = ref<boolean | null>(null)
const diagrams = ref<readonly DiagramSummary[]>([])
const chosen = ref(typeof route.params.artifactId === 'string' ? route.params.artifactId : '')
const showBreaches = ref(true)
const serverPictureUrl = ref<string | null>(null)

/** The lab lays out ArchiMate diagrams, the family the layout implementation covers. */
const isArchimate = (diagram: DiagramSummary): boolean => diagram.diagram_type.startsWith('archimate-')

const layoutJson = computed(() => JSON.stringify({ layout: lab.layout.value }, null, 2))

const breachRows = computed(() => {
  const relations = new Map((lab.geometry.value?.relations ?? []).map((relation) => [relation.index, relation]))
  const named = (alias: string) =>
    lab.geometry.value?.elements.find((one) => one.alias === alias)?.label
    ?? lab.geometry.value?.boxes.find((one) => one.alias === alias)?.label
    ?? alias
  return lab.breaches.value.map((breach) => {
    const relation = relations.get(breach.relation)
    return { ...breach, between: relation ? `${named(relation.source)} → ${named(relation.target)}` : '' }
  })
})

watch(() => lab.serverPicture.value, (svg) => {
  if (serverPictureUrl.value) URL.revokeObjectURL(serverPictureUrl.value)
  serverPictureUrl.value = svg ? URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' })) : null
})

watch(chosen, (artifactId) => {
  void router.replace(layoutLabRoute(artifactId))
  if (artifactId) void lab.load(artifactId)
})

const copyLayout = async () => {
  try {
    await navigator.clipboard.writeText(layoutJson.value)
    toast('Layout JSON copied')
  } catch {
    toast('Could not copy: select the JSON below instead', 'warn')
  }
}

const onKey = (event: KeyboardEvent) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    lab.undo()
  }
}

onMounted(async () => {
  labIsOn.value = await layoutLabIsOn()
  if (!labIsOn.value) return
  window.addEventListener('keydown', onKey)
  const listed = await Effect.runPromise(svc.listDiagrams()).catch(() => null)
  diagrams.value = [...(listed?.items ?? [])]
    .filter(isArchimate)
    .sort((one, other) => one.name.localeCompare(other.name))
  if (chosen.value) void lab.load(chosen.value)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  if (serverPictureUrl.value) URL.revokeObjectURL(serverPictureUrl.value)
})
</script>

<template>
  <section class="lab">
    <header class="lab__header">
      <h1>Layout lab</h1>
      <p class="lab__note">
        Move and resize elements and boxes of a real diagram. Nothing is saved.
      </p>
    </header>

    <p
      v-if="labIsOn === false"
      class="lab__off"
    >
      The layout lab is switched off. Start the backend with <code>ARCH_LAYOUT_LAB=1</code> to use it.
    </p>

    <template v-else-if="labIsOn">
      <div class="lab__toolbar">
        <label>
          Diagram
          <select
            v-model="chosen"
            data-testid="layout-lab-diagram"
          >
            <option value="">Choose an ArchiMate diagram…</option>
            <option
              v-for="diagram in diagrams"
              :key="diagram.artifact_id"
              :value="diagram.artifact_id"
            >{{ diagram.name }}</option>
          </select>
        </label>
        <button
          type="button"
          :disabled="lab.history.value.length === 0"
          title="Undo (Ctrl+Z)"
          @click="lab.undo()"
        >
          Undo
        </button>
        <button
          type="button"
          :disabled="!lab.geometry.value"
          title="Return to PlantUML's arrangement"
          @click="lab.reset()"
        >
          Reset
        </button>
        <button
          type="button"
          :disabled="!lab.geometry.value"
          @click="lab.routeEverything()"
        >
          Route all lines
        </button>
        <button
          type="button"
          :disabled="!lab.geometry.value"
          title="Open every gap too narrow for its lines, as a first layout is written down"
          data-testid="layout-lab-widen"
          @click="lab.widen()"
        >
          Widen narrow gaps
        </button>
        <label class="lab__toggle">
          <input
            v-model="showBreaches"
            type="checkbox"
          >
          Show breaches
        </label>
        <span
          v-if="lab.routes.value"
          class="lab__counts"
          data-testid="layout-lab-counts"
        >
          <span class="lab__count lab__count--hard">{{ lab.counts.value.hard }} hard</span>
          <span class="lab__count lab__count--soft">{{ lab.counts.value.soft }} soft</span>
        </span>
        <span
          v-else-if="lab.geometry.value"
          class="lab__counts"
        >PlantUML's lines: drag something, or route all, to route them</span>
        <span
          v-if="lab.timing.value"
          class="lab__timing"
        >{{ lab.timing.value.kind }} pass {{ lab.timing.value.ms.toFixed(0) }} ms</span>
        <button
          type="button"
          :disabled="!lab.geometry.value || lab.serverLoading.value"
          data-testid="layout-lab-server"
          @click="lab.askServer()"
        >
          {{ lab.serverLoading.value ? 'Composing…' : 'Server picture' }}
        </button>
        <button
          type="button"
          :disabled="!lab.geometry.value"
          @click="copyLayout"
        >
          Copy layout JSON
        </button>
      </div>

      <p v-if="lab.loading.value">
        Reading PlantUML's picture…
      </p>
      <p
        v-if="lab.error.value"
        class="lab__error"
      >
        {{ lab.error.value }}
      </p>

      <LayoutLabCanvas
        v-if="lab.geometry.value"
        :lab="lab"
        :show-breaches="showBreaches"
      />

      <div
        v-if="lab.geometry.value"
        class="lab__panels"
      >
        <section class="lab__panel">
          <h2>Server picture</h2>
          <p
            v-if="lab.serverError.value"
            class="lab__error"
          >
            {{ lab.serverError.value }}
          </p>
          <img
            v-if="serverPictureUrl"
            :src="serverPictureUrl"
            alt="The server's composed picture of this layout"
            class="lab__server"
            data-testid="layout-lab-server-picture"
          >
          <p v-else-if="!lab.serverError.value">
            Ask for it to compare the composer's drawing of this layout with the live one.
          </p>
        </section>
        <section class="lab__panel">
          <h2>Breaches</h2>
          <ul class="lab__breaches">
            <li
              v-for="(row, index) in breachRows"
              :key="index"
              :class="`lab__breach lab__breach--${row.tier}`"
            >
              <strong>{{ row.rule }}</strong> ({{ row.tier }}) — {{ row.between }}
            </li>
          </ul>
          <h2>Layout JSON</h2>
          <pre class="lab__json">{{ layoutJson }}</pre>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.lab__header h1 { font-size: 20px; }
.lab__note { color: #475569; margin-bottom: 12px; }
.lab__off { padding: 12px 16px; background: #fef3c7; border: 1px solid #f59e0b; border-radius: 6px; }
.lab__toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.lab__toolbar select { margin-left: 6px; max-width: 360px; }
.lab__toolbar button { padding: 4px 10px; border: 1px solid #cbd5e1; border-radius: 4px; }
.lab__toolbar button { background: #fff; cursor: pointer; }
.lab__toolbar button:disabled { opacity: 0.5; cursor: default; }
.lab__counts { display: inline-flex; gap: 6px; color: #475569; }
.lab__count { padding: 1px 8px; border-radius: 10px; font-weight: 600; }
.lab__count--hard { background: #fee2e2; color: #991b1b; }
.lab__count--soft { background: #fef3c7; color: #92400e; }
.lab__timing { color: #64748b; font-size: 12px; }
.lab__error { color: #b91c1c; }
.lab__panels { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-top: 12px; }
.lab__panel { background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; min-width: 0; }
.lab__panel h2 { font-size: 14px; margin: 4px 0 8px; }
.lab__server { max-width: 100%; height: auto; }
.lab__breaches { list-style: none; max-height: 240px; overflow: auto; font-size: 12px; }
.lab__breach--hard strong { color: #b91c1c; }
.lab__breach--soft strong { color: #b45309; }
.lab__json { max-height: 240px; overflow: auto; font-size: 11px; background: #f8fafc; padding: 6px; }
</style>
