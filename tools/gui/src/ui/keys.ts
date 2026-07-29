import type { InjectionKey } from 'vue'
import type { ModelService } from '../application/ModelService'

export const modelServiceKey: InjectionKey<ModelService> = Symbol('modelService')
export const toastKey: InjectionKey<(message: string, type?: 'info' | 'warn' | 'error', durationMs?: number) => void> = Symbol('toast')
