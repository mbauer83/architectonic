/**
 * A candidate edited on its own picture (06·5, F12): the diagram editor's own session (`useDiagramEditing`)
 * over the picture the candidate is the subject of (`candidatePicture`), which needs no stored diagram. What
 * the session does is recorded in the candidate as it is made, so the candidate saves as you go and no diagram
 * is ever written:
 *
 * - a content command (create, rename, relate, delete…) is recorded as an edit (`candidateCanvas.editsOf`);
 * - an element of the model put on the picture is a reference: the candidate reads over it (its `scope`);
 * - *Remove from view* takes a reference away again; an element the candidate creates or changes stays.
 *
 * **Undo reverts what was recorded, not only the picture.** Each content step is remembered with what the
 * candidate held after it — its operations and its references — keyed by the session's own list of commands
 * and of additions, which a move carries over unchanged. When Undo or Redo returns the session to a list it has
 * held before, the candidate is written back to what it held then, through its versioned edit.
 */
import { ref, watch, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import { stableEntityId } from '../../domain/artifactId'
import { chosenIds, commandsOf, editsOf, operationsOf } from '../../domain/candidates/candidateCanvas'
import type { Point } from '../../domain/layout/geometry'
import type { ScopedEntity } from '../../domain/schemas/candidates'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { formatEffectError } from '../lib/errors'
import { candidatePicture } from './pictureSource'
import type { DiagramEditing, StartMembership } from './useDiagramEditing'
import { useDiagramEditing } from './useDiagramEditing'

/** The key of a session state that holds no content commands, or no additions, yet. */
const NONE: readonly CanvasCommand[] = Object.freeze([])
const NO_ADDITIONS: ReadonlyMap<string, string> = new Map()

/** What the candidate holds that the canvas changes: its operations, and the model elements it reads over. */
interface Held { readonly changes: unknown; readonly scope: readonly string[] }

/** What *one* is called in the candidate's view; empty where its record states no name. */
const scopedName = (one: ScopedEntity): string => (typeof one.fields.name === 'string' ? one.fields.name : '')

/**
 * What the candidate reads over that the model holds (*view*) and the picture does not start with (*drawn*), by
 * name: put on the picture as the session opens.
 */
const undrawn = (
  scope: readonly string[], drawn: readonly string[], view: readonly ScopedEntity[],
): Map<string, string> => {
  const starts = new Set(drawn.map(stableEntityId))
  const names = new Map(view.map((one) => [stableEntityId(one.id), scopedName(one)]))
  return new Map(scope.flatMap((id) => {
    const name = names.get(stableEntityId(id))
    return starts.has(stableEntityId(id)) || name === undefined ? [] : [[id, name] as const]
  }))
}

const scopeOf = (record: Readonly<Record<string, unknown>>): readonly string[] =>
  Array.isArray(record.scope) ? record.scope.filter((one): one is string => typeof one === 'string') : []

export function useCandidateEditing(
  svc: ModelService, membership: StartMembership, candidateId: () => string, onRecorded: () => void,
): DiagramEditing & { readonly savedAt: Ref<string | null> } {
  const editing = useDiagramEditing(svc, candidatePicture(svc, candidateId), membership)
  const savedAt = ref<string | null>(null)
  let version = ''
  let held: Held = { changes: null, scope: [] }
  const recordedAt = new Map<readonly CanvasCommand[], Map<ReadonlyMap<string, string>, Held>>()
  /** One write at a time, in the order they were asked for: each states the version the one before answered. */
  let writing: Promise<unknown> = Promise.resolve()

  const commandsNow = (): readonly CanvasCommand[] => editing.session.state.value?.commands ?? NONE
  const additionsNow = (): ReadonlyMap<string, string> => editing.session.state.value?.additions ?? NO_ADDITIONS
  const remember = () => {
    const byAdditions = recordedAt.get(commandsNow()) ?? new Map<ReadonlyMap<string, string>, Held>()
    recordedAt.set(commandsNow(), byAdditions.set(additionsNow(), held))
  }
  const stamp = () => { savedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  const queued = <T>(write: () => Promise<T>): Promise<T> => {
    const next = writing.then(write, write)
    writing = next.catch(() => undefined)
    return next
  }
  const answered = (answer: { readonly record: Readonly<Record<string, unknown>>; readonly version: string }) => {
    version = answer.version
    held = { changes: answer.record.changes, scope: scopeOf(answer.record) }
  }
  /** Run *write* in the queue, then remember the step and say it was saved; a refusal says why on the canvas. */
  const recording = async (write: () => Promise<void>): Promise<boolean> => {
    try {
      await queued(write)
      remember()
      stamp()
      onRecorded()
      return true
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
      return false
    }
  }
  /** Record that the candidate reads over *scope*; run inside a recording, which queues it. */
  const readOver = async (scope: readonly string[]): Promise<void> => {
    answered(await Effect.runPromise(svc.editCandidate(candidateId(), version, { scope })))
  }

  /**
   * Read the candidate, and open its picture with what it already creates, renames and connects drawn, and the
   * model elements it reads over that the picture does not start with.
   */
  const open = async (): Promise<boolean> => {
    try {
      const [read, composed] = await Promise.all([
        Effect.runPromise(svc.readCandidate(candidateId())),
        Effect.runPromise(svc.compareCandidate(candidateId(), 'model')),
      ])
      answered(read)
      recordedAt.clear()
      const starts = membership(null)?.entity_ids ?? []
      const referenced = undrawn(held.scope, starts, composed.view.entities)
      const commands = commandsOf(operationsOf(read.record), chosenIds(composed.view), [...starts, ...referenced.keys()])
      const opened = await editing.open(commands, referenced)
      remember()
      return opened
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
      return false
    }
  }

  /** Draw the command, then record it in the candidate; a refused record says why on the canvas. */
  const propose = async (
    proposed: CanvasCommand | readonly CanvasCommand[], overlay?: Record<string, unknown>,
    place?: readonly [string, Point],
  ): Promise<boolean> => {
    if (!(await editing.propose(proposed, overlay, place))) return false
    return recording(async () => {
      for (const edit of [proposed].flat().flatMap(editsOf)) {
        answered(await Effect.runPromise(svc.recordOperation(candidateId(), version, edit)))
      }
    })
  }

  /** Put the model's element *id* on the picture, and record that the candidate reads over it. */
  const add: DiagramEditing['add'] = async (id, name, type, at) => {
    const before = additionsNow()
    await editing.add(id, name, type, at)
    if (additionsNow() === before) return
    const known = held.scope.some((one) => stableEntityId(one) === stableEntityId(id))
    await recording(async () => { if (!known) await readOver([...held.scope, id]) })
  }

  /** Remove *aliases* from view; the model elements among them are no longer read over by the candidate. */
  const remove: DiagramEditing['remove'] = (aliases) => {
    const before = editing.session.state.value
    // Read off the picture before the removal, which takes them off it.
    const gone = new Set(aliases.flatMap((alias) => {
      const key = editing.session.geometry.value?.elements.find((one) => one.alias === alias)?.key
      return key === undefined ? [] : [stableEntityId(key)]
    }))
    editing.remove(aliases)
    if (editing.session.state.value === before) return
    const kept = held.scope.filter((one) => !gone.has(stableEntityId(one)))
    void recording(async () => { if (kept.length !== held.scope.length) await readOver(kept) })
  }

  /** The candidate written back to *then*, what it held when the session last showed this. */
  const restore = async (then: Held): Promise<void> => {
    try {
      const wrote = await queued(async () => {
        if (then.changes === held.changes && then.scope === held.scope) return false
        answered(await Effect.runPromise(svc.editCandidate(candidateId(), version, {
          changes: then.changes, scope: [...then.scope],
        })))
        held = then
        return true
      })
      if (!wrote) return
      stamp()
      onRecorded()
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
    }
  }

  // Undo and Redo show lists the session held before; a new step shows ones it has not. The comparison is
  // made in the queue, after any record still in flight has answered.
  watch([commandsNow, additionsNow], ([commands, additions]) => {
    const then = recordedAt.get(commands)?.get(additions)
    if (then !== undefined) void restore(then)
  }, { flush: 'sync' })

  return { ...editing, open, propose, add, remove, savedAt }
}
