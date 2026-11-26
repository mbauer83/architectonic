<script setup lang="ts">
/**
 * Asks for the git credential a remote refused an operation for: the SSH key passphrase, or an
 * HTTPS token (and username, for hosts that bind it).
 *
 * The value is handed to the caller once and the fields are cleared; the backend keeps it in memory
 * for its process lifetime and never sends it back. Nothing here stores it, and the fields opt out of
 * the browser's autofill so it is not offered for saving either.
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import type { GitCredentialAnswer, GitCredentialRequest } from '../lib/gitCredentials'

const props = defineProps<{ request: GitCredentialRequest }>()
const emit = defineEmits<{ submit: [answer: GitCredentialAnswer]; cancel: [] }>()

const secret = ref('')
const username = ref('')

const isSsh = computed(() => props.request.protocol === 'ssh')
const title = computed(() => (isSsh.value ? 'SSH key passphrase' : 'HTTPS credentials'))
const secretLabel = computed(() => (isSsh.value ? 'Passphrase' : 'Token or password'))

const clear = (): void => {
  secret.value = ''
  username.value = ''
}

const submit = (): void => {
  if (!secret.value) return
  const answer: GitCredentialAnswer = isSsh.value || !username.value.trim()
    ? { secret: secret.value }
    : { secret: secret.value, username: username.value.trim() }
  clear()
  emit('submit', answer)
}

const cancel = (): void => {
  clear()
  emit('cancel')
}

onBeforeUnmount(clear)
</script>

<template>
  <div
    class="dialog-overlay"
    @mousedown.self="cancel"
  >
    <form
      class="dialog"
      role="dialog"
      :aria-label="title"
      autocomplete="off"
      @submit.prevent="submit"
    >
      <div class="dialog__header">
        <span class="dialog__title">{{ title }}</span>
      </div>
      <div class="dialog__body">
        <p
          v-if="request.rejected"
          class="dialog__reason"
          role="alert"
        >
          The remote refused the {{ isSsh ? 'passphrase' : 'credentials' }} given. Enter
          {{ isSsh ? 'it' : 'them' }} again.
        </p>
        <p class="dialog__hint">
          The repository's remote <code>{{ request.remote }}</code> asks for
          {{ isSsh ? 'the passphrase of your SSH key' : 'a username and token' }}. The backend keeps
          {{ isSsh ? 'it' : 'them' }} in memory until it stops, and never writes {{ isSsh ? 'it' : 'them' }} to disk.
        </p>
        <div
          v-if="!isSsh"
          class="field"
        >
          <label
            class="field__label"
            for="git-credential-username"
          >Username (optional)</label>
          <input
            id="git-credential-username"
            v-model="username"
            class="field__input"
            type="text"
            autocomplete="off"
            spellcheck="false"
          >
        </div>
        <div class="field">
          <label
            class="field__label"
            for="git-credential-secret"
          >{{ secretLabel }}</label>
          <input
            id="git-credential-secret"
            v-model="secret"
            class="field__input"
            type="password"
            autocomplete="off"
            spellcheck="false"
          >
        </div>
      </div>
      <div class="dialog__footer">
        <button
          type="button"
          class="btn btn--cancel"
          @click="cancel"
        >
          Cancel
        </button>
        <button
          type="submit"
          class="btn btn--primary"
          :disabled="!secret"
        >
          Continue
        </button>
      </div>
    </form>
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
  z-index: 300;
}
.dialog {
  background: var(--surface);
  border-radius: 8px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, .22);
  width: clamp(320px, 90vw, 440px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dialog__header { padding: 14px 18px 12px; border-bottom: 1px solid var(--border); }
.dialog__title { font-size: 14px; font-weight: 700; color: var(--text); }
.dialog__body { padding: 18px; display: flex; flex-direction: column; gap: 12px; }
.dialog__hint { font-size: 13px; color: var(--text-2); line-height: 1.5; overflow-wrap: anywhere; }
.dialog__hint code {
  background: var(--soft);
  border-radius: 3px;
  padding: 1px 5px;
  font-family: monospace;
  font-size: 12px;
}
.dialog__reason {
  font-size: 12px;
  color: var(--danger-strong);
  background: var(--danger-soft);
  border: 1px solid var(--danger-border);
  border-radius: 5px;
  padding: 8px 10px;
}
.field { display: flex; flex-direction: column; gap: 5px; }
.field__label { font-size: 12px; font-weight: 600; color: var(--text-2); }
.field__input {
  padding: 7px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  outline: none;
}
.field__input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-ring); }
.dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--hair);
}
.btn { padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: none; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--cancel { background: var(--soft); color: var(--text-2); border: 1px solid var(--border-strong); }
.btn--primary { background: var(--accent); color: var(--on-accent); }
.btn--primary:hover:not(:disabled) { background: var(--accent-strong); }
</style>
