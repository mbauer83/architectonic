<script setup lang="ts">
import { inject, ref, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { modelServiceKey } from '../keys'
import { searchHitRoute } from '../lib/searchNavigation'
import { useQuery } from '../composables/useQuery'
import type { SearchResult } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()

const searchState = useQuery<SearchResult, RepoError>()

const query = ref((route.query.q as string | undefined) ?? '')

const submit = () => {
  if (!query.value.trim()) return
  void router.replace({ path: '/search', query: { q: query.value } })
  searchState.run(svc.search(query.value.trim()))
}

if (query.value) searchState.run(svc.search(query.value.trim()))

watch(() => route.query.q, (q) => {
  query.value = (q as string | undefined) ?? ''
  if (query.value) searchState.run(svc.search(query.value.trim()))
})

const friendlyName = (id: string) => {
  const parts = id.split('.')
  return parts.length > 2 ? parts.slice(2).join(' ').replace(/-/g, ' ') : id
}
</script>

<template>
  <div>
    <h1 class="page-title">
      Search
    </h1>

    <form
      class="search-form"
      @submit.prevent="submit"
    >
      <input
        v-model="query"
        class="search-input"
        type="text"
        placeholder="Search entities, connections, diagrams…"
        autofocus
      >
      <button
        type="submit"
        class="search-btn"
      >
        Search
      </button>
    </form>

    <div
      v-if="searchState.loading.value"
      class="state-msg"
    >
      Searching…
    </div>
    <div
      v-else-if="searchState.errorMessage.value"
      class="state-msg state-msg--error"
    >
      {{ searchState.errorMessage.value }}
    </div>

    <template v-else-if="searchState.data.value">
      <p class="result-count">
        {{ searchState.data.value.hits.length }} result{{ searchState.data.value.hits.length !== 1 ? 's' : '' }} for "{{ searchState.data.value.query }}"
      </p>

      <div
        v-if="!searchState.data.value.hits.length"
        class="state-msg"
      >
        No results found.
      </div>

      <ul class="result-list">
        <li
          v-for="h in searchState.data.value.hits"
          :key="h.artifact_id"
          class="result-item card"
        >
          <div class="result-top">
            <RouterLink
              v-if="searchHitRoute(h)"
              :to="searchHitRoute(h)!"
              class="result-name"
            >
              {{ h.name || friendlyName(h.artifact_id) }}
            </RouterLink>
            <span
              v-else
              class="result-name"
            >{{ h.name || friendlyName(h.artifact_id) }}</span>
            <span class="score">{{ h.score.toFixed(1) }}</span>
          </div>
          <div class="result-meta">
            <span class="mono result-type">{{ h.artifact_type }}</span>
            <span
              v-if="h.is_global"
              class="global-chip"
            >enterprise</span>
            <span
              v-if="h.domain"
              class="domain-badge"
              :class="`domain--${h.domain}`"
            >{{ h.domain }}</span>
            <span
              class="status-badge"
              :class="`status--${h.status}`"
            >{{ h.status }}</span>
          </div>
          <div class="result-id mono">
            {{ h.artifact_id }}
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 20px; }

.search-form { display: flex; gap: 8px; margin-bottom: 20px; }
.search-input {
  flex: 1;
  padding: 9px 14px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  font-size: 14px;
  outline: none;
}
.search-input:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,.15); }
.search-btn {
  padding: 9px 20px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.search-btn:hover { background: #1d4ed8; }

.state-msg { color: #6b7280; }
.state-msg--error { color: #dc2626; }

.result-count { font-size: 13px; color: #6b7280; margin-bottom: 12px; }

.result-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }

.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 14px 16px; }

.result-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.result-name { font-weight: 600; font-size: 14px; }
.score { font-size: 11px; color: #9ca3af; font-family: monospace; }

.result-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
.result-type { font-size: 12px; color: #374151; }
.result-id { font-size: 11px; color: #9ca3af; }
.mono { font-family: monospace; }

.global-chip {
  display: inline-block;
  background: #fef3c7; color: #92400e;
  border: 1px solid #fde68a; border-radius: 3px;
  padding: 0 5px; font-size: 10px; font-weight: 600;
}
</style>
