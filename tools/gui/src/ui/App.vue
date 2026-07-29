<script setup lang="ts">
import { RouterView } from 'vue-router'
import { inject, provide, ref } from 'vue'
import { modelServiceKey, toastKey } from './keys'
import NavBar from './components/NavBar.vue'
import ToastStack from './components/ToastStack.vue'
import SaveChangesDialog from './components/SaveChangesDialog.vue'
import { useSyncCoordination } from './composables/useSyncCoordination'

type SaveMode = 'engagement-save' | 'enterprise-save' | 'enterprise-submit' | 'enterprise-withdraw'

const svc = inject(modelServiceKey)!
const saveDialogMode = ref<SaveMode | null>(null)

const toasts = ref<Array<{id: number; message: string; type: 'info'|'warn'|'error'}>>([])
let toastCounter = 0

const addToast = (message: string, type: 'info'|'warn'|'error' = 'info', durationMs = 4000) => {
  const id = ++toastCounter
  toasts.value.push({ id, message, type })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, durationMs)
}

const {
  adminMode, readOnly, anyWriteBlocked, authorityKnown, authority,
  syncStatus, engDirty, entStatus, loadSyncStatus,
} = useSyncCoordination(svc, addToast)

provide('writeBlocked', anyWriteBlocked)
provide(toastKey, addToast)
</script>

<template>
  <NavBar
    :eng-dirty="engDirty"
    :ent-status="entStatus"
    :authority-known="authorityKnown"
    :authority="authority"
    @open-save-dialog="saveDialogMode = $event"
  />

  <output
    v-if="adminMode"
    class="admin-banner"
  >
    <strong>Admin mode</strong> — writes to both repositories are permitted.
    Use the <strong>Changes</strong> menu in the header to save and submit enterprise changes.
  </output>

  <output
    v-if="readOnly"
    class="readonly-banner"
  >
    <strong>Read-only mode</strong> — write operations are disabled.
  </output>

  <main class="main">
    <RouterView />
  </main>

  <ToastStack :toasts="toasts" />

  <SaveChangesDialog
    v-if="saveDialogMode"
    :mode="saveDialogMode"
    :sync-status="syncStatus"
    @close="saveDialogMode = null"
    @done="(msg) => { addToast(msg); loadSyncStatus() }"
  />
</template>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; font-size: 14px; line-height: 1.5; color: #1a1a1a; background: #f5f5f5; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
pre, code { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 13px; }
</style>

<style scoped>
.admin-banner { background: #7c2d12; color: #fed7aa; padding: 7px 24px; font-size: 13px; line-height: 1.5; border-bottom: 2px solid #ea580c; }
.admin-banner strong { color: #fb923c; font-weight: 700; }
.readonly-banner { background: #1e3a5f; color: #bfdbfe; padding: 7px 24px; font-size: 13px; line-height: 1.5; border-bottom: 2px solid #3b82f6; }
.readonly-banner strong { color: #93c5fd; font-weight: 700; }
.main { max-width: 1200px; margin: 0 auto; padding: 24px; }
</style>
