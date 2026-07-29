<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { inject } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { SyncStatus, SyncChangesResult } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import { useQuery } from '../composables/useQuery'
import { useMutation } from '../composables/useMutation'

type DialogMode =
  | 'engagement-save'
  | 'enterprise-save'
  | 'enterprise-submit'
  | 'enterprise-withdraw'

const props = defineProps<{
  mode: DialogMode
  syncStatus: SyncStatus | null
}>()

const emit = defineEmits<{
  close: []
  done: [message: string]
}>()

const svc = inject(modelServiceKey)!

const commitMessage = ref('')
const pushToRemote = ref(true)

const changesQuery = useQuery<SyncChangesResult, RepoError>()
const saveMutation = useMutation<string, RepoError>()

const artifacts = computed(() => changesQuery.data.value?.artifacts ?? [])
const displayError = computed(() => changesQuery.errorMessage.value ?? saveMutation.errorMessage.value)

const repoScope = computed((): 'engagement' | 'enterprise' =>
  props.mode.startsWith('enterprise') ? 'enterprise' : 'engagement',
)

onMounted(() => {
  if (props.mode === 'engagement-save' || props.mode === 'enterprise-save') {
    changesQuery.run(svc.getChanges(repoScope.value))
  }
})

const title = computed(() => {
  switch (props.mode) {
    case 'engagement-save': return 'Save Engagement Changes'
    case 'enterprise-save': return 'Save Enterprise Changes'
    case 'enterprise-submit': return 'Submit for Review'
    case 'enterprise-withdraw': return 'Discard Submission'
    default: return 'Save Changes'
  }
})

const entStatus = computed(() => props.syncStatus?.enterprise ?? null)
const branchName = computed(() => entStatus.value?.branch ?? null)

const confirmLabel = computed(() => {
  if (saveMutation.running.value) {
    switch (props.mode) {
      case 'engagement-save': return 'Saving…'
      case 'enterprise-save': return 'Saving…'
      case 'enterprise-submit': return 'Submitting…'
      case 'enterprise-withdraw': return 'Discarding…'
    }
  }
  switch (props.mode) {
    case 'engagement-save': return 'Save & Commit'
    case 'enterprise-save': return 'Save & Commit'
    case 'enterprise-submit': return 'Submit for Review'
    case 'enterprise-withdraw': return 'Discard Submission'
    default: return 'Continue'
  }
})

const needsCommitMessage = computed(
  () => props.mode === 'engagement-save' || props.mode === 'enterprise-save',
)

const canSubmit = computed(() => {
  if (saveMutation.running.value) return false
  if (saveMutation.result.value) return false
  if (needsCommitMessage.value && !commitMessage.value.trim()) return false
  return true
})

const buildSaveEffect = (): Effect.Effect<string, RepoError, never> => {
  switch (props.mode) {
    case 'engagement-save':
      return Effect.map(
        svc.saveEngagementChanges({ message: commitMessage.value.trim(), push: pushToRemote.value }),
        (res) => res.commit
          ? `Committed ${res.commit.slice(0, 8)}${res.pushed ? ' and pushed' : ''}`
          : 'Saved (nothing to commit)',
      )
    case 'enterprise-save':
      return Effect.map(
        svc.saveEnterpriseChanges({ message: commitMessage.value.trim() }),
        (res) => res.commit
          ? `Committed ${res.commit.slice(0, 8)} on branch ${res.branch ?? branchName.value ?? 'unknown'}`
          : 'Saved (nothing to commit)',
      )
    case 'enterprise-submit':
      return Effect.map(
        svc.submitEnterpriseChanges(),
        (res) => res.already_submitted
          ? `Already submitted on branch ${res.branch ?? branchName.value ?? 'unknown'}`
          : `Branch ${res.branch ?? 'unknown'} ready — open a pull request to merge into the enterprise repository`,
      )
    case 'enterprise-withdraw':
      // A no-op withdraw is a 400 from the backend now (never a silent success),
      // so a success here always names the discarded branch.
      return Effect.map(
        svc.withdrawEnterpriseChanges(),
        (res) => res.discarded_branch ? `Branch ${res.discarded_branch} discarded` : 'Submission withdrawn',
      )
  }
}

const execute = async () => {
  if (!canSubmit.value) return
  const exit = await saveMutation.run(buildSaveEffect())
  if (Exit.isSuccess(exit)) emit('done', exit.value)
}
</script>

<template>
  <div
    class="dialog-overlay"
    @mousedown.self="emit('close')"
  >
    <div
      class="dialog"
      role="dialog"
      :aria-label="title"
    >
      <div class="dialog__header">
        <span class="dialog__title">{{ title }}</span>
        <button
          class="dialog__close"
          aria-label="Close"
          @click="emit('close')"
        >
          ×
        </button>
      </div>

      <div class="dialog__body">
        <!-- Changes summary (save modes only) -->
        <div
          v-if="!saveMutation.result.value && (mode === 'engagement-save' || mode === 'enterprise-save')"
          class="changes-panel"
        >
          <div
            v-if="changesQuery.loading.value"
            class="changes-loading"
          >
            Loading changes…
          </div>
          <template v-else-if="artifacts.length">
            <div class="changes-header">
              {{ artifacts.length }} artifact{{ artifacts.length !== 1 ? 's' : '' }} changed
            </div>
            <ul class="changes-list">
              <li
                v-for="a in artifacts"
                :key="a.artifact_id"
                class="change-row"
              >
                <span
                  class="change-status"
                  :class="`change-status--${a.file_status}`"
                >{{ a.file_status[0].toUpperCase() }}</span>
                <span class="change-name">{{ a.name !== a.artifact_id ? a.name : '' }}</span>
                <code class="change-id">{{ a.artifact_id }}</code>
                <span
                  v-if="a.changes.length"
                  class="change-tags"
                >
                  <span
                    v-for="c in a.changes"
                    :key="c"
                    class="change-tag"
                  >{{ c }}</span>
                </span>
              </li>
            </ul>
          </template>
          <div
            v-else
            class="changes-empty"
          >
            No tracked changes detected
          </div>
        </div>

        <!-- Success state -->
        <div
          v-if="saveMutation.result.value"
          class="result-msg"
        >
          <div class="result-text">
            {{ saveMutation.result.value }}
          </div>
          <div
            v-if="mode === 'enterprise-submit'"
            class="result-hint"
          >
            Push the branch and open a pull request in your enterprise repository to complete the review.
          </div>
        </div>

        <!-- Engagement save form -->
        <template v-else-if="mode === 'engagement-save'">
          <div class="field">
            <label
              class="field__label"
              for="sc-commit-msg"
            >Commit message</label>
            <input
              id="sc-commit-msg"
              v-model="commitMessage"
              class="field__input"
              type="text"
              placeholder="Describe your changes…"
              :disabled="saveMutation.running.value"
              @keydown.enter.prevent="execute"
            >
          </div>
          <label class="checkbox-row">
            <input
              v-model="pushToRemote"
              type="checkbox"
              :disabled="saveMutation.running.value"
            >
            <span>Push to remote</span>
          </label>
        </template>

        <!-- Enterprise save form -->
        <template v-else-if="mode === 'enterprise-save'">
          <p class="dialog__hint">
            Changes are committed to a local branch
            <code v-if="branchName">{{ branchName }}</code> and can be submitted for review later.
          </p>
          <div class="field">
            <label
              class="field__label"
              for="sc-ent-msg"
            >Commit message</label>
            <input
              id="sc-ent-msg"
              v-model="commitMessage"
              class="field__input"
              type="text"
              placeholder="Describe your changes…"
              :disabled="saveMutation.running.value"
              @keydown.enter.prevent="execute"
            >
          </div>
        </template>

        <!-- Enterprise submit confirmation -->
        <template v-else-if="mode === 'enterprise-submit'">
          <p class="dialog__hint">
            This will finalize the branch
            <code v-if="branchName">{{ branchName }}</code>
            and mark it ready for review.
            All uncommitted changes must be saved first.
          </p>
          <p
            v-if="entStatus?.commits_ahead"
            class="dialog__hint"
          >
            {{ entStatus.commits_ahead }} commit(s) ahead of enterprise main.
          </p>
        </template>

        <!-- Enterprise withdraw confirmation -->
        <template v-else-if="mode === 'enterprise-withdraw'">
          <p class="dialog__hint dialog__hint--warn">
            This will discard the submission branch
            <code v-if="branchName">{{ branchName }}</code>
            and all unpromoted enterprise changes will be lost.
          </p>
        </template>

        <div
          v-if="displayError"
          class="error-msg"
        >
          {{ displayError }}
        </div>
      </div>

      <div class="dialog__footer">
        <button
          class="btn btn--cancel"
          :disabled="saveMutation.running.value"
          @click="emit('close')"
        >
          {{ saveMutation.result.value ? 'Close' : 'Cancel' }}
        </button>
        <button
          v-if="!saveMutation.result.value"
          class="btn"
          :class="mode === 'enterprise-withdraw' ? 'btn--danger' : 'btn--primary'"
          :disabled="!canSubmit"
          @click="execute"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.dialog {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, .22);
  width: clamp(320px, 90vw, 480px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dialog__header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px 12px; border-bottom: 1px solid #e5e7eb; }
.dialog__title { font-size: 14px; font-weight: 700; color: #111827; }
.dialog__close { background: none; border: none; font-size: 20px; line-height: 1; color: #6b7280; cursor: pointer; padding: 0 2px; }
.dialog__close:hover { color: #111827; }

.dialog__body { padding: 18px; display: flex; flex-direction: column; gap: 12px; }

.dialog__hint { font-size: 13px; color: #4b5563; line-height: 1.5; }
.dialog__hint code { background: #f3f4f6; border-radius: 3px; padding: 1px 5px; font-family: monospace; font-size: 12px; }
.dialog__hint--warn { color: #92400e; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field__label { font-size: 12px; font-weight: 600; color: #374151; }
.field__input { padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; color: #111827; outline: none; }
.field__input:focus { border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,.15); }
.field__input:disabled { background: #f9fafb; color: #9ca3af; }
.checkbox-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #374151; cursor: pointer; }
.result-msg { display: flex; flex-direction: column; gap: 6px; }
.result-text { font-size: 13px; font-weight: 600; color: #166534; }
.result-hint { font-size: 12px; color: #4b5563; }
.error-msg { font-size: 12px; color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; border-radius: 5px; padding: 8px 10px; }
.dialog__footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid #f3f4f6; }
.btn { padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: none; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--cancel { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
.btn--cancel:hover:not(:disabled) { background: #e5e7eb; }
.btn--primary { background: #2563eb; color: #fff; }
.btn--primary:hover:not(:disabled) { background: #1d4ed8; }
.btn--danger { background: #dc2626; color: #fff; }
.btn--danger:hover:not(:disabled) { background: #b91c1c; }

.changes-panel { border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden; max-height: 220px; display: flex; flex-direction: column; }
.changes-loading, .changes-empty { padding: 10px 12px; font-size: 12px; color: #6b7280; }
.changes-header { padding: 6px 12px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; background: #f9fafb; border-bottom: 1px solid #e5e7eb; flex-shrink: 0; }
.changes-list { list-style: none; overflow-y: auto; flex: 1; }
.change-row { display: flex; align-items: baseline; gap: 6px; padding: 6px 12px 15px 12px; font-size: 12px; border-bottom: 1px solid #f3f4f6; }
.change-row:last-child { border-bottom: none; }
.change-status { font-size: 10px; font-weight: 800; width: 14px; flex-shrink: 0; }
.change-status--added { color: #16a34a; }
.change-status--modified { color: #2563eb; }
.change-status--deleted { color: #dc2626; }
.change-name { font-weight: 500; color: #111827; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.change-id { color: #6b7280; font-size: 11px; flex-shrink: 0; }
.change-tags { display: flex; gap: 3px; flex-shrink: 0; }
.change-tag { background: #eff6ff; color: #1d4ed8; border-radius: 3px; padding: 1px 5px; font-size: 10px; font-weight: 600; }
</style>
