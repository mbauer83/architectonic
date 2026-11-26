// @vitest-environment jsdom
/**
 * A detail page names each write by the artifact's tier and the mode the app shell read, and offers it
 * by the permission answer for that write.
 *
 * Regression: the entity and diagram detail pages each fetched the backend's mode themselves and hid
 * or showed their controls by it, beside the permission answer the backend already projects; an
 * enterprise artifact's Delete was decided by `isGlobal && !adminMode` rather than by the answer for
 * the admin write, which says `admin_mode_required` in words.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, defineComponent, h, nextTick, ref, type App } from 'vue'
import PermittedButton from '../../components/PermittedButton.vue'
import { useArtifactWrites } from '../useArtifactWrites'
import { adminModeKey, permissionsKey } from '../../keys'
import { permissionOf } from '../../../domain/permissions'
import type { SyncAuthority } from '../../../domain/schemas/sync-status'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.innerHTML = '' })

const ADMIN_WRITES = ['admin_update_entity', 'admin_delete_entity', 'admin_create_connection',
  'admin_delete_connection', 'admin_delete_diagram']

/** The backend's answer outside admin mode: every admin write refused for that reason, the rest allowed. */
const outsideAdminMode: SyncAuthority = {
  block_kind: 'none', blocked_reason: null, blocked_message: null, denied_intents: {},
  denied_operations: {
    ...Object.fromEntries(ADMIN_WRITES.map((name) => [name, { denied: true, code: 'admin_mode_required' }] as const)),
    entities_update_entity: { denied: false, code: null },
    entities_delete_entity: { denied: false, code: null },
  },
}

const deleteButton = async (enterprise: boolean, adminMode?: boolean) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const Probe = defineComponent(() => {
    const writes = useArtifactWrites(() => enterprise)
    return () => h(PermittedButton, { operation: writes.value.deleteEntity }, () => 'Delete')
  })
  app = createApp({ render: () => h(Probe) })
  app.provide(permissionsKey, computed(() => (operation: string) =>
    permissionOf({ known: true, authority: outsideAdminMode, writesPaused: false }, operation)))
  if (adminMode !== undefined) app.provide(adminModeKey, ref(adminMode))
  app.mount(host)
  await nextTick()
  return host.querySelector('button')!
}

describe('an artifact\'s writes on a detail page', () => {
  it('offers an engagement entity\'s Delete by the engagement write', async () => {
    expect((await deleteButton(false)).disabled).toBe(false)
  })

  it('refuses an enterprise entity\'s Delete outside admin mode, saying why', async () => {
    const button = await deleteButton(true, false)
    expect(button.disabled).toBe(true)
    expect(button.title).toBe('Only a backend in admin mode writes to the enterprise repository')
  })

  it('takes the backend not to be in admin mode where the shell said nothing', () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    let upstream: boolean | null = null
    app = createApp(defineComponent(() => {
      upstream = useArtifactWrites(() => true).value.upstream
      return () => h('span')
    }))
    app.mount(host)
    expect(upstream).toBe(false)
  })
})
