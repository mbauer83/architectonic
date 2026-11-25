/**
 * The permission answer a test mounts a component under, as the app shell provides it. Without one every
 * operation is refused (`usePermissions`), so a test of what a control does gives it the answer it needs.
 */
import { computed, type App } from 'vue'
import { ALLOWED, type Permission } from '../../../domain/permissions'
import { permissionsKey } from '../../keys'

/** *app* answered: every operation in *refused* refused for *reason*, every other allowed. */
export const answered = (app: App, refused: readonly string[] = [], reason = 'Not permitted for your role'): App =>
  app.provide(permissionsKey, computed(() => (operation: string): Permission =>
    (refused.includes(operation) ? { allowed: false, reason } : ALLOWED)))
