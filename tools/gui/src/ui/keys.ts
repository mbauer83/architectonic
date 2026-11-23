import type { InjectionKey } from 'vue'
import type { ModelService } from '../application/ModelService'

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
