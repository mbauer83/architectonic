/**
 * The permission answer, read where a control is offered (`useCan`), or a whole table of commands at once
 * (`useCommandPermission`). It generalises `useWriteBlock`: one answer per named operation rather than
 * one switch for every write, and with the reason a control says when it is refused.
 *
 * With nothing provided — a component mounted outside the app shell — every operation is refused, as it
 * is before the backend has answered: a control is never offered on a permission no one gave.
 */
import { computed, inject, toValue, type ComputedRef, type InjectionKey, type MaybeRefOrGetter } from 'vue'
import { ALLOWED, NO_ANSWER_YET, type Permission } from '../../domain/permissions'
import { type Can, permissionsKey } from '../keys'
import { type CanvasCommandName, type CommandOperations, DIAGRAM_OPERATIONS } from '../components/canvasCommands'

const UNANSWERED: ComputedRef<Can> = computed(() => () => ({ allowed: false, reason: NO_ANSWER_YET }))

export const usePermissions = (): ComputedRef<Can> => inject(permissionsKey, UNANSWERED)

/** Whether *operation* may be done now, and why not. */
export const useCan = (operation: MaybeRefOrGetter<string>): ComputedRef<Permission> => {
  const can = usePermissions()
  return computed(() => can.value(toValue(operation)))
}

/** The operations the canvas's commands are on the page it is on: provided by the canvas editor. */
export const canvasOperationsKey: InjectionKey<CommandOperations> = Symbol('canvasOperations')

export type CommandPermission = (command: CanvasCommandName) => Permission

/**
 * Whether each canvas command may be done now: by the operation it is on this page (*operations*, else
 * the canvas editor's), and never refused where it writes nothing.
 */
export const useCommandPermission = (operations?: CommandOperations): ComputedRef<CommandPermission> => {
  const can = usePermissions()
  const table = operations ?? inject(canvasOperationsKey, DIAGRAM_OPERATIONS)
  return computed(() => (command) => {
    const operation = table[command]
    return operation === null ? ALLOWED : can.value(operation)
  })
}
