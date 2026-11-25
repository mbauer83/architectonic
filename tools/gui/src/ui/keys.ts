import type { ComputedRef, InjectionKey } from 'vue'
import type { ModelService } from '../application/ModelService'
import type { Permission } from '../domain/permissions'

export const modelServiceKey: InjectionKey<ModelService> = Symbol('modelService')
/** What a toast offers to do, such as *Undo*: pressing it runs it and closes the toast. */
export interface ToastAction {
  readonly label: string
  readonly run: () => void
}
export type ShowToast = (
  message: string, type?: 'info' | 'warn' | 'error', durationMs?: number, action?: ToastAction,
) => void
export const toastKey: InjectionKey<ShowToast> = Symbol('toast')

/** Whether a named operation may be done now, and why not (`domain/permissions`). */
export type Can = (operation: string) => Permission
/** The app shell's permission answer, provided once (`useSyncCoordination`) and read by `usePermissions`. */
export const permissionsKey: InjectionKey<ComputedRef<Can>> = Symbol('permissions')
