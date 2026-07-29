<script setup lang="ts">
import { ref, inject, watch, computed, onUnmounted } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import { useEntityFilters } from '../composables/useEntityFilters'
import type { EntityDisplayInfo, ReferenceSearchHit } from '../../domain'
import { dividerIndex, entityDisplayInfoToHit } from './EntityPickerInput.helpers'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import EntityPickerFixedRows from './EntityPickerFixedRows.vue'
import { toGlyphKey } from '../lib/glyphKey'
import {
  calcHasStageUI,
  calcCanGoBack,
  calcCanGoForward,
} from './EntityPickerInput.helpers'
import type { PickerHit, WidenableTo } from './EntityPickerInput.helpers'

type Stage = 'scope' | 'entity-type'

const props = defineProps<{
  excludedIds?: Set<string>
  placeholder?: string
  fixedDomains?: string[]
  fixedEntityTypes?: string[]
  widenableTo?: WidenableTo
  acceptedTypes?: Set<string>
  diagramType?: string
  /** Narrow the palette/picker to this viewpoint's scope, intersected with diagramType's. */
  viewpoint?: string
  /** Collapse the results dropdown once a pick is made — off by default so the many
   * "add several entities in a row" consumers (diagram/matrix creation) keep browsing
   * without re-opening; a single-value consumer (e.g. a parameter prompt) opts in so its
   * own controls below the picker aren't left covered by a dropdown with nothing left to
   * do. */
  closeOnSelect?: boolean
}>()
const emit = defineEmits<{ select: [entity: EntityDisplayInfo] }>()

const svc = inject(modelServiceKey)!
const { selectedDomains, selectedEntityTypes, domainOptions, availableEntityTypes, impliedDomains, toggle } =
  useEntityFilters({ fixedEntityTypes: props.fixedEntityTypes })

const query = ref('')
const results = ref<PickerHit[]>([])
const open = ref(false)
const busy = ref(false)
const loadingMore = ref(false)
const nextCursor = ref<string | null>(null)
const activeResultIdx = ref(-1)
const inputRef = ref<HTMLInputElement | null>(null)
const wrapRef = ref<HTMLElement | null>(null)
const chipRowRef = ref<HTMLElement | null>(null)
const navRef = ref<HTMLElement | null>(null)
const sentinelRef = ref<HTMLLIElement | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
let sentinelObserver: IntersectionObserver | null = null

// ── Dropdown positioning (fixed to viewport so it never extends page height) ──

const dropStyle = ref<Record<string, string>>({})

const computeDropPos = () => {
  const rect = inputRef.value?.getBoundingClientRect()
  if (!rect) return
  const minW = Math.max(280, rect.width)
  const left = Math.min(rect.left, window.innerWidth - minW - 12)
  dropStyle.value = {
    top: `${rect.bottom + 3}px`,
    left: `${Math.max(0, left)}px`,
    minWidth: `${minW}px`,
    maxHeight: `${Math.max(120, window.innerHeight - rect.bottom - 12)}px`,
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    computeDropPos()
    window.addEventListener('scroll', computeDropPos, true)
    window.addEventListener('resize', computeDropPos)
  } else {
    window.removeEventListener('scroll', computeDropPos, true)
    window.removeEventListener('resize', computeDropPos)
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', computeDropPos, true)
  window.removeEventListener('resize', computeDropPos)
  sentinelObserver?.disconnect()
})

// ── Stage ──────────────────────────────────────────────────────────────────────

const initialStage = computed<Stage>(() => props.fixedDomains?.length ? 'entity-type' : 'scope')
const currentStage = ref<Stage>(initialStage.value)

const hasStageUI = computed(() =>
  calcHasStageUI(props.fixedDomains, props.fixedEntityTypes, props.widenableTo),
)
const stageTitle = computed(() =>
  currentStage.value === 'scope' ? '1. Filter Domains' : '2. Filter Entity Types',
)
const canGoBack = computed(() =>
  calcCanGoBack(currentStage.value, props.fixedDomains, props.widenableTo),
)
const canGoForward = computed(() =>
  calcCanGoForward(currentStage.value, props.fixedEntityTypes, props.widenableTo),
)

const effectiveDomains = computed(() => [
  ...(props.fixedDomains ?? []),
  ...selectedDomains.value,
  ...impliedDomains.value,
])
const effectiveEntityTypes = computed(() => [...(props.fixedEntityTypes ?? []), ...selectedEntityTypes.value])

const summaryParts = computed(() => {
  const parts: string[] = []
  if (effectiveDomains.value.length) parts.push(`Domains: ${effectiveDomains.value.join(', ')}`)
  if (effectiveEntityTypes.value.length) parts.push(`Types: ${effectiveEntityTypes.value.join(', ')}`)
  return parts
})

// ── Search ─────────────────────────────────────────────────────────────────────

const acceptHits = (items: readonly EntityDisplayInfo[]): PickerHit[] =>
  items.map(entityDisplayInfoToHit).filter(r =>
    !props.excludedIds?.has(r.artifact_id)
    && (!props.acceptedTypes || props.acceptedTypes.has(String(r.artifact_type))),
  )

const searchParams = (cursor?: string) => ({
  query: query.value.trim() || '',
  limit: 30,
  diagramType: props.diagramType,
  viewpoint: props.viewpoint,
  domains: effectiveDomains.value.length ? effectiveDomains.value : undefined,
  entityTypes: effectiveEntityTypes.value.length ? effectiveEntityTypes.value : undefined,
  cursor,
})

const doSearch = async () => {
  busy.value = true
  nextCursor.value = null
  const exit = await Effect.runPromiseExit(svc.searchEntityDisplay(searchParams()))
  busy.value = false
  if (Exit.isSuccess(exit)) {
    results.value = acceptHits(exit.value.items)
    nextCursor.value = exit.value.next_cursor
    activeResultIdx.value = -1
  }
}

const loadMore = async () => {
  if (!nextCursor.value || loadingMore.value) return
  loadingMore.value = true
  const exit = await Effect.runPromiseExit(svc.searchEntityDisplay(searchParams(nextCursor.value)))
  loadingMore.value = false
  if (Exit.isSuccess(exit)) {
    results.value = [...results.value, ...acceptHits(exit.value.items)]
    nextCursor.value = exit.value.next_cursor
  }
}

const scheduleSearch = () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => void doSearch(), 200)
}

watch(sentinelRef, (el) => {
  sentinelObserver?.disconnect()
  sentinelObserver = null
  if (!el) return
  sentinelObserver = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting) void loadMore()
  })
  sentinelObserver.observe(el)
})

const openDropdown = () => {
  currentStage.value = initialStage.value
  open.value = true
  void doSearch()
}

const onInput = () => { open.value = true; scheduleSearch() }

const internalDividerIdx = computed(() => dividerIndex(results.value))

const pick = async (hit: ReferenceSearchHit) => {
  const exit = await Effect.runPromiseExit(svc.getEntityDisplayItem(hit.artifact_id))
  if (!Exit.isSuccess(exit)) return
  // Focus before emit: prevents the focused li from being the element removed
  // from DOM (which would shift focus to <body> and reset window scroll).
  inputRef.value?.focus({ preventScroll: true })
  activeResultIdx.value = -1
  if (props.closeOnSelect) open.value = false
  emit('select', exit.value)
  // excludedIds watcher removes the picked item reactively — no full re-fetch
  // needed, which avoids flickering from replacing the entire results array.
}

const toggleDomain = (d: string) => {
  if (props.fixedDomains?.includes(d)) return
  selectedDomains.value = toggle(selectedDomains.value, d)
  selectedEntityTypes.value = selectedEntityTypes.value.filter(t => availableEntityTypes.value.includes(t))
  scheduleSearch()
}

const toggleEntityType = (t: string) => {
  if (props.fixedEntityTypes?.includes(t)) return
  selectedEntityTypes.value = toggle(selectedEntityTypes.value, t)
  scheduleSearch()
}

const goBack = () => { currentStage.value = 'scope'; selectedEntityTypes.value = [] }
const goForward = () => { currentStage.value = 'entity-type' }

// ── Keyboard helpers ───────────────────────────────────────────────────────────

const chipEls = () => [...(chipRowRef.value?.querySelectorAll<HTMLElement>('.chip') ?? [])]
const resultEls = () => [...(wrapRef.value?.querySelectorAll<HTMLElement>('[data-result]') ?? [])]
const navEl = () => navRef.value?.querySelector<HTMLElement>('button') ?? null

const focusResult = (idx: number) => { activeResultIdx.value = idx; resultEls()[idx]?.focus() }
const focusAfterNav = () => { const c = chipEls(); if (c.length) c[0].focus(); else focusResult(0) }
const focusBeforeChips = () => { const n = navEl(); if (n) n.focus(); else inputRef.value?.focus() }

const onInputKeydown = (e: KeyboardEvent) => {
  if (!open.value) { if (e.key === 'ArrowDown' || e.key === 'Enter') openDropdown(); return }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    const n = navEl()
    if (n) n.focus(); else focusAfterNav()
  } else if (e.key === 'Escape') { open.value = false; activeResultIdx.value = -1 }
}

const onNavKeydown = (e: KeyboardEvent) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); focusAfterNav() }
  else if (e.key === 'ArrowUp') { e.preventDefault(); inputRef.value?.focus() }
  else if (e.key === 'Escape') { open.value = false; inputRef.value?.focus() }
}

const onChipKeydown = (e: KeyboardEvent, i: number) => {
  const chips = chipEls()
  if (e.key === 'ArrowDown') { e.preventDefault(); focusResult(0) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); focusBeforeChips() }
  else if (e.key === 'ArrowRight') { e.preventDefault(); chips[i + 1]?.focus() }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); chips[i - 1]?.focus() }
  else if (e.key === 'Escape') { open.value = false; inputRef.value?.focus() }
}

const onResultKeydown = (e: KeyboardEvent, hit: PickerHit, i: number) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); void pick(hit) }
  else if (e.key === 'ArrowDown') { e.preventDefault(); focusResult(Math.min(i + 1, results.value.length - 1)) }
  else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (i > 0) { focusResult(i - 1) } else {
      const chips = chipEls()
      if (chips.length) chips[0].focus(); else { const n = navEl(); if (n) n.focus(); else inputRef.value?.focus() }
    }
  } else if (e.key === 'Escape') { open.value = false; inputRef.value?.focus() }
}

const onFocusOut = (e: FocusEvent) => {
  if (!wrapRef.value?.contains(e.relatedTarget as Node))
    setTimeout(() => { open.value = false }, 100)
}

watch(() => props.excludedIds, () => {
  results.value = results.value.filter(r => !props.excludedIds?.has(r.artifact_id))
})
watch([selectedDomains, selectedEntityTypes], scheduleSearch)
</script>

<template>
  <div
    ref="wrapRef"
    class="ep"
    @focusout="onFocusOut"
  >
    <input
      ref="inputRef"
      v-model="query"
      class="ep-inp"
      type="search"
      autocomplete="off"
      :placeholder="placeholder ?? 'Search entities…'"
      @input="onInput"
      @focus="openDropdown"
      @keydown="onInputKeydown"
    >

    <div
      v-if="open"
      class="ep-drop"
      :style="dropStyle"
      @mousedown.prevent
    >
      <EntityPickerFixedRows
        :fixed-domains="fixedDomains"
        :fixed-entity-types="fixedEntityTypes"
      />

      <!-- Interactive filter stage (hidden when widenableTo=none or all levels are fixed) -->
      <div
        v-if="hasStageUI"
        class="ep-stage"
      >
        <div class="ep-stage-hdr">
          <span class="ep-stage-title">{{ stageTitle }}</span>
          <div
            ref="navRef"
            class="ep-nav"
          >
            <button
              v-if="canGoBack"
              class="nav-btn"
              type="button"
              @click="goBack"
              @keydown="onNavKeydown"
            >
              ← Back
            </button>
            <button
              v-if="canGoForward"
              class="nav-btn nav-btn--fwd"
              type="button"
              @click="goForward"
              @keydown="onNavKeydown"
            >
              Entity Types →
            </button>
          </div>
        </div>

        <div
          ref="chipRowRef"
          class="ep-chips"
        >
          <template v-if="currentStage === 'scope'">
            <button
              v-for="(d, i) in domainOptions"
              :key="d.key"
              class="chip"
              :class="{
                'chip--on': effectiveDomains.includes(d.key),
                'chip--fixed': fixedDomains?.includes(d.key),
                'chip--implied': impliedDomains.includes(d.key) && !selectedDomains.includes(d.key) && !fixedDomains?.includes(d.key),
              }"
              type="button"
              :title="impliedDomains.includes(d.key) && !selectedDomains.includes(d.key) ? 'Derived from selected entity type' : undefined"
              @click="toggleDomain(d.key)"
              @keydown="(e) => onChipKeydown(e, i)"
            >
              {{ d.label }}
            </button>
          </template>
          <template v-else>
            <button
              v-for="(t, i) in availableEntityTypes"
              :key="t"
              class="chip chip--sm"
              :class="{ 'chip--on': effectiveEntityTypes.includes(t), 'chip--fixed': fixedEntityTypes?.includes(t) }"
              type="button"
              @click="toggleEntityType(t)"
              @keydown="(e) => onChipKeydown(e, i)"
            >
              {{ t }}
            </button>
          </template>
        </div>

        <div
          v-if="summaryParts.length"
          class="ep-summary"
        >
          {{ summaryParts.join(' · ') }}
        </div>
      </div>

      <!-- Results -->
      <div
        v-if="busy"
        class="ep-state"
      >
        Searching…
      </div>
      <ul
        v-else-if="results.length"
        class="ep-results"
        role="listbox"
      >
        <li
          v-if="query.trim()"
          class="ep-note"
          aria-hidden="true"
        >
          showing best matches for "{{ query.trim() }}"
        </li>
        <template
          v-for="(r, i) in results"
          :key="r.artifact_id"
        >
          <li
            v-if="i === internalDividerIdx"
            class="ep-divider"
            aria-hidden="true"
          >
            diagram-internal
          </li>
          <li
            data-result
            role="option"
            class="ep-result"
            :class="{ 'ep-result--hi': i === activeResultIdx }"
            tabindex="0"
            @mousedown.prevent="void pick(r)"
            @keydown="onResultKeydown($event, r, i)"
            @focus="activeResultIdx = i"
          >
            <span
              v-if="r.artifact_type"
              class="ep-glyph"
            >
              <ArchimateTypeGlyph
                :type="toGlyphKey(r.artifact_type)"
                :size="14"
              />
            </span>
            <span class="ep-name">{{ r.name }}</span>
            <span class="ep-meta">{{ r.artifact_type ?? r.record_type }} · {{ r.domain }}</span>
          </li>
        </template>
        <li
          v-if="nextCursor"
          ref="sentinelRef"
          class="ep-sentinel"
          aria-hidden="true"
        >
          {{ loadingMore ? 'Loading more…' : '' }}
        </li>
      </ul>
      <div
        v-else
        class="ep-state"
      >
        {{ query.trim() ? 'No matches.' : 'Type to search or apply filters.' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.ep { position: relative; }
.ep-inp { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; outline: none; box-sizing: border-box; }
.ep-inp:focus { border-color: #2563eb; box-shadow: 0 0 0 2px #bfdbfe; }

.ep-drop {
  position: fixed; z-index: 1000;
  background: white; border: 1px solid #d1d5db; border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0,0,0,.13); overflow-y: auto;
}


.ep-stage { padding: 10px 10px 6px; border-bottom: 1px solid #f3f4f6; background: #f8fafc; }
.ep-stage-hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.ep-stage-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #475569; }
.ep-nav { display: flex; gap: 6px; }
.nav-btn { border: 1px solid #cbd5e1; background: white; color: #334155; border-radius: 6px; padding: 4px 9px; font-size: 11px; font-weight: 600; cursor: pointer; }
.nav-btn:hover { background: #f8fafc; }
.nav-btn--fwd { background: #dbeafe; border-color: #bfdbfe; color: #1d4ed8; }
.nav-btn--fwd:hover { background: #bfdbfe; }

.ep-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid #cbd5e1; background: white; border-radius: 999px; padding: 5px 11px; font-size: 12px; color: #334155; cursor: pointer; outline: none; }
.chip:hover:not(.chip--fixed), .chip:focus:not(.chip--fixed) { border-color: #2563eb; color: #1d4ed8; }
.chip--sm { font-size: 11px; padding: 4px 9px; }
.chip--on { background: #0f172a; border-color: #0f172a; color: white; }
.chip--fixed { opacity: .6; cursor: default; }
.chip--implied { border-style: dashed; border-color: #6366f1; color: #4338ca; background: #eef2ff; }

.ep-summary { margin-top: 7px; font-size: 11px; color: #64748b; }

.ep-results { margin: 0; padding: 4px 0; list-style: none; }
.ep-result { display: flex; align-items: center; gap: 8px; padding: 7px 10px; cursor: pointer; outline: none; }
.ep-result:hover, .ep-result:focus, .ep-result--hi { background: #eff6ff; }
.ep-sentinel { height: 24px; font-size: 11px; color: #9ca3af; text-align: center; line-height: 24px; }
.ep-glyph { flex-shrink: 0; color: #4b5563; display: flex; align-items: center; }
.ep-name { flex: 1; font-weight: 500; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ep-meta { font-size: 11px; color: #9ca3af; white-space: nowrap; }
.ep-state { font-size: 12px; color: #9ca3af; padding: 10px 12px; }
.ep-note { font-size: 10.5px; color: #94a3b8; padding: 3px 10px; font-style: italic; }
.ep-divider { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #94a3b8; padding: 6px 10px 2px; border-top: 1px solid #e5e7eb; margin-top: 4px; }
</style>
