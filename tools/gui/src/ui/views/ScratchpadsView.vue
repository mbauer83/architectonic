<script setup lang="ts">
/**
 * The scratchpads, and the way to start one.
 *
 * Creating is a name, and nothing else — a scratchpad exists because the typed path asks for
 * decisions before anything has been decided, so its own entry form must not ask for any either.
 * The four frames are seeded server-side, so a new scratchpad opens usable rather than blank.
 *
 * It used to ask for a **model-project** to file the scratchpad under, which was the one question
 * the feature exists to postpone: a lift chooses its target per *frame*, so a canvas holding
 * strategy work for one project and delivery work for another had to be filed under one of them
 * before a word of it was written. The folder is now the server's default.
 */
import { computed, inject, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Exit } from 'effect'
import { modelServiceKey } from '../keys'
import { useMutation } from '../composables/useMutation'
import { useQuery } from '../composables/useQuery'
import { scratchpadDetailRoute } from '../router/artifactRoutes'
import type { Scratchpad, ScratchpadList } from '../../domain/schemas/scratchpads'
import type { RepoError } from '../../ports/repositoryErrors'

const svc = inject(modelServiceKey)!
const router = useRouter()

const listQuery = useQuery<ScratchpadList, RepoError>()
const createMutation = useMutation<Scratchpad, RepoError>()

const newName = ref('')

const scratchpads = computed(() => listQuery.data.value?.scratchpads ?? [])
const canCreate = computed(() => newName.value.trim().length > 0)

const load = (): void => {
  listQuery.run(svc.listScratchpads())
}
onMounted(load)

const create = async (): Promise<void> => {
  if (!canCreate.value) return
  const exit = await createMutation.run(
    svc.createScratchpad({ name: newName.value.trim() }),
  )
  if (Exit.isSuccess(exit)) {
    newName.value = ''
    await router.push(scratchpadDetailRoute(exit.value['artifact-id']))
  }
}
</script>

<template>
  <section class="page">
    <header>
      <h1>Scratchpads</h1>
      <p class="lead">
        Somewhere to think before anything is decided. Write notes, draw links between them, and
        keep whatever does not become model content.
      </p>
    </header>

    <form
      class="new"
      data-testid="new-scratchpad"
      @submit.prevent="create"
    >
      <input
        v-model="newName"
        type="text"
        placeholder="What are you thinking about?"
        data-testid="new-scratchpad-name"
        aria-label="Scratchpad name"
      >
      <button
        type="submit"
        :disabled="!canCreate || createMutation.running.value"
      >
        New scratchpad
      </button>
    </form>
    <p
      v-if="createMutation.errorMessage.value"
      class="err"
    >
      {{ createMutation.errorMessage.value }}
    </p>

    <p
      v-if="listQuery.loading.value"
      class="state"
    >
      Loading…
    </p>
    <p
      v-else-if="listQuery.errorMessage.value"
      class="err"
    >
      {{ listQuery.errorMessage.value }}
    </p>
    <p
      v-else-if="scratchpads.length === 0"
      class="state"
      data-testid="scratchpads-empty"
    >
      Nothing yet. A scratchpad is the cheapest place to put a half-formed thought.
    </p>
    <ul
      v-else
      class="list"
      data-testid="scratchpad-list"
    >
      <li
        v-for="pad in scratchpads"
        :key="pad['artifact-id']"
      >
        <RouterLink
          class="row"
          :to="scratchpadDetailRoute(pad['artifact-id'])"
        >
          <span class="name">{{ pad.name }}</span>
          <span class="meta">
            <span class="mono">{{ pad.group }}</span>
            <span class="dot">·</span>{{ pad['note-count'] }} note{{ pad['note-count'] === 1 ? '' : 's' }}
            <span class="dot">·</span>{{ pad.status }}
          </span>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.page { max-width: 900px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.lead { margin: 0 0 20px; color: #6b7280; font-size: 13px; max-width: 62ch; }
.new { display: flex; gap: 8px; margin-bottom: 18px; }
.new input { flex: 1; padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; }
.new select { padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; }
.new button {
  padding: 7px 14px; border: 1px solid #2563eb; border-radius: 6px; background: #2563eb;
  color: #fff; font-size: 13px; cursor: pointer;
}
.new button:disabled { opacity: .5; cursor: default; }
.list { list-style: none; padding: 0; margin: 0; }
.row {
  display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
  padding: 11px 12px; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 8px;
  text-decoration: none; color: inherit; background: #fff;
}
.row:hover { border-color: #c7d2fe; background: #f8faff; }
.name { font-size: 14px; font-weight: 500; }
.meta { font-size: 12px; color: #6b7280; }
.mono { font-family: ui-monospace, monospace; }
.dot { margin: 0 6px; color: #d1d5db; }
.state { color: #6b7280; font-size: 13px; }
.err { color: #dc2626; font-size: 13px; }
</style>
