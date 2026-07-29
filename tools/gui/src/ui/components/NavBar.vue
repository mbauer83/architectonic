<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { computed, inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { searchHitRoute } from '../lib/searchNavigation'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import SyncStatusCluster from './SyncStatusCluster.vue'
import type { EnterpriseSyncStatus, SearchHit, SyncAuthority } from '../../domain'
import { readErrorMessage } from '../lib/errors'

type SaveMode = 'engagement-save' | 'enterprise-save' | 'enterprise-submit' | 'enterprise-withdraw'

defineProps<{
  engDirty: boolean
  entStatus: EnterpriseSyncStatus | null
  authorityKnown: boolean
  authority: SyncAuthority | null
}>()

const emit = defineEmits<{ openSaveDialog: [mode: SaveMode] }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()

// A viewpoint-driven execution surface (/entities?viewpoint=…, /graph?viewpoint=…)
// belongs to Viewpoints in the user's mental model — highlight follows the origin, not
// the host path.
const viewpointDriven = computed(() => Boolean(route.query.viewpoint))

const browseTo = computed(() => {
  const q: Record<string, string> = {}
  const { domain, view, type } = route.query
  if (domain) q.domain = domain as string
  if (view) q.view = view as string
  if (type) q.type = type as string
  return Object.keys(q).length ? { path: '/entities', query: q } : '/entities'
})

const searchQuery = ref('')
type SearchDropdownHit = SearchHit | {
  record_type: 'entity'
  artifact_id: string
  name: string
  artifact_type: string
}

const searchHits = ref<SearchDropdownHit[]>([])
const showDropdown = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const onSearchInput = () => {
  const q = searchQuery.value.trim()
  if (debounceTimer) clearTimeout(debounceTimer)
  if (q.length < 2) { searchHits.value = []; showDropdown.value = false; return }
  debounceTimer = setTimeout(() => {
    void Effect.runPromise(svc.search(q, 20))
      .then((result) => {
        const raw = result.hits
        const seen = new Set<string>()
        const resolved: SearchDropdownHit[] = []
        for (const hit of raw) {
          if (hit.record_type !== 'connection' && !seen.has(hit.artifact_id)) {
            seen.add(hit.artifact_id)
            resolved.push(hit)
          }
        }
        const entityNames = new Map(resolved.map((hit) => [hit.artifact_id, hit.name]))
        searchHits.value = resolved.slice(0, 12).map((hit) => ({
          ...hit,
          name: entityNames.get(hit.artifact_id) ?? hit.artifact_id,
        }))
        showDropdown.value = searchHits.value.length > 0
      })
      .catch((error: unknown) => {
        console.error('Search failed', readErrorMessage(error))
        searchHits.value = []
        showDropdown.value = false
      })
  }, 280)
}

const selectHit = (hit: SearchDropdownHit) => {
  showDropdown.value = false; searchQuery.value = ''; searchHits.value = []
  const to = searchHitRoute(hit)
  if (to) void router.push(to)
}
const submitSearch = () => {
  const q = searchQuery.value.trim()
  if (!q) return
  showDropdown.value = false
  void router.push({ path: '/search', query: { q } })
  searchQuery.value = ''; searchHits.value = []
}
const onSearchBlur = () => { setTimeout(() => { showDropdown.value = false }, 180) }
const onSearchFocus = () => { if (searchHits.value.length > 0) showDropdown.value = true }
const hitGlyphType = (hit: SearchDropdownHit) =>
  (hit.record_type === 'diagram' || hit.record_type === 'connection') ? 'generic' : (hit.artifact_type ?? 'generic')
const hitTypeLabel = (hit: SearchDropdownHit) => (hit.artifact_type || hit.record_type || '').replace(/^archimate[-_]/i, '')

const assuranceStatus = ref<'unlocked' | 'locked' | 'not_initialised' | null>(null)
onMounted(async () => {
  try {
    const resp = await fetch('/api/assurance/status')
    if (resp.ok) {
      const data = await resp.json() as { status: string }
      assuranceStatus.value = data.status as 'unlocked' | 'locked' | 'not_initialised'
    }
  } catch { /* assurance store unavailable — suppress */ }
})
</script>

<template>
  <header class="nav">
    <RouterLink
      class="nav__brand"
      to="/"
    >
      Architecture Repository
    </RouterLink>
    <nav
      class="nav__links"
      aria-label="Primary"
    >
      <RouterLink
        :to="browseTo"
        :class="{ 'nav__link--suppressed': viewpointDriven }"
      >
        Browse
      </RouterLink>
      <RouterLink to="/documents">
        Documents
      </RouterLink>
      <RouterLink to="/diagrams">
        Diagrams
      </RouterLink>
      <RouterLink
        to="/viewpoints"
        :class="{ 'nav__link--forced-active': viewpointDriven }"
      >
        Viewpoints
      </RouterLink>
      <RouterLink
        v-if="assuranceStatus !== null"
        to="/assurance"
        :title="assuranceStatus === 'unlocked' ? 'Assurance store unlocked' : 'Assurance store locked'"
      >
        {{ assuranceStatus === 'unlocked' ? '🔓' : '🔒' }} Assurance
      </RouterLink>
    </nav>
    <div
      class="nav__workflow"
      role="group"
      aria-label="Workflow and status"
    >
      <SyncStatusCluster
        :authority-known="authorityKnown"
        :authority="authority"
        :enterprise="entStatus"
        :engagement-dirty="engDirty"
        @open-save-dialog="emit('openSaveDialog', $event)"
      />
      <form
        class="nav__search"
        @submit.prevent="submitSearch"
      >
        <input
          v-model="searchQuery"
          class="nav__search-input"
          type="search"
          placeholder="Search…"
          aria-label="Search"
          autocomplete="off"
          @input="onSearchInput"
          @focus="onSearchFocus"
          @blur="onSearchBlur"
        >
        <div
          v-if="showDropdown"
          class="nav__search-dropdown"
        >
          <button
            v-for="hit in searchHits"
            :key="hit.artifact_id"
            class="nav__search-item"
            @mousedown.prevent="selectHit(hit)"
          >
            <ArchimateTypeGlyph
              :type="hitGlyphType(hit)"
              :size="14"
              class="nav__search-item-glyph"
            />
            <span class="nav__search-item-name">{{ hit.name || hit.artifact_id }}</span>
            <span class="nav__search-item-type">{{ hitTypeLabel(hit) }}</span>
          </button>
        </div>
      </form>
    </div>
  </header>
</template>

<style scoped>
.nav { display: flex; align-items: center; gap: 20px; padding: 0 24px; height: 48px; background: #1e293b; color: #f8fafc; position: sticky; top: 0; z-index: 10; }
.nav__brand { font-weight: 600; font-size: 15px; color: #f8fafc; white-space: nowrap; flex-shrink: 0; }
.nav__brand:hover { text-decoration: none; color: #93c5fd; }
/* Wrap order: the primary links shrink and truncate FIRST; the workflow/status
   landmark and search keep their size (flex-shrink: 0). */
.nav__links { display: flex; gap: 4px; flex-wrap: nowrap; min-width: 0; overflow: hidden; flex: 1; }
.nav__links a { color: #b0bec5; font-size: 13px; padding: 4px 8px; border-radius: 4px; white-space: nowrap; }
.nav__links a.router-link-active { color: #f8fafc; font-weight: 500; background: #2d3f55; }
.nav__links a:hover { color: #f1f5f9; text-decoration: none; background: #263347; }
.nav__links a.nav__link--suppressed.router-link-active { color: #b0bec5; font-weight: 400; background: transparent; }
.nav__links a.nav__link--forced-active { color: #f8fafc; font-weight: 500; background: #2d3f55; }
.nav__workflow { margin-inline-start: auto; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.nav__search { display: flex; align-items: center; flex-shrink: 0; position: relative; }
.nav__search-input { width: clamp(140px, 18vw, 260px); padding: 5px 10px; border-radius: 5px; border: 1px solid #334155; background: #0f172a; color: #f1f5f9; font-size: 13px; outline: none; transition: width .2s, border-color .15s; }
.nav__search-input::placeholder { color: #64748b; }
.nav__search-input:focus { width: clamp(180px, 22vw, 340px); border-color: #475569; background: #1e293b; }
.nav__search-input::-webkit-search-cancel-button { display: none; }
.nav__search-dropdown { position: absolute; top: calc(100% + 4px); right: 0; width: 100%; min-width: 0; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,.18); max-height: 320px; overflow-y: auto; z-index: 100; }
.nav__search-item { display: flex; align-items: flex-start; gap: 7px; width: 100%; padding: 8px 12px; border: none; background: none; cursor: pointer; text-align: left; font-size: 13px; color: #1a1a1a; }
.nav__search-item:hover { background: #f1f5f9; }
.nav__search-item-glyph { flex-shrink: 0; color: #6b7280; margin-top: 1px; }
.nav__search-item-name { flex: 1; font-weight: 500; }
.nav__search-item-type { font-size: 11px; color: #64748b; white-space: nowrap; flex-shrink: 0; }
@media (max-width: 1060px) {
  .nav { gap: 12px; padding: 0 16px; }
}
@media (max-width: 820px) {
  .nav__brand { font-size: 13px; }
  .nav__search-input { width: clamp(80px, 12vw, 160px) !important; }
}
</style>
