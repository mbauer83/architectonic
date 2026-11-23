/**
 * A candidate edited on the scope diagram's canvas (06·5, F12): the diagram editor's own session
 * (`useDiagramEditing`), with every content command recorded at once in the candidate as an edit
 * (`candidateCanvas.editsOf`), so the candidate saves as you go and the diagram is never written.
 * *Remove from view* is the session's own removal and records nothing.
 */
import { ref, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { commandsOf, editsOf, operationsOf } from '../../domain/stressAnalysis/candidateCanvas'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { formatEffectError } from '../lib/errors'
import type { DiagramEditing } from './useDiagramEditing'
import { useDiagramEditing } from './useDiagramEditing'

export function useCandidateEditing(
  svc: ModelService, diagramId: () => string, membership: () => DrawnMembership | null,
  candidateId: () => string, onRecorded: () => void,
): DiagramEditing & { readonly savedAt: Ref<string | null> } {
  const editing = useDiagramEditing(svc, diagramId, membership)
  const savedAt = ref<string | null>(null)
  let version = ''

  /** Read the candidate, and open the canvas with what it already creates, renames and connects drawn. */
  const open = async (): Promise<boolean> => {
    try {
      const read = await Effect.runPromise(svc.readCandidate(candidateId()))
      version = read.version
      return await editing.open(commandsOf(operationsOf(read.record)))
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
      return false
    }
  }

  /** Draw the command, then record it in the candidate; a refused record says why on the canvas. */
  const propose = async (command: CanvasCommand, overlay?: Record<string, unknown>): Promise<boolean> => {
    if (!(await editing.propose(command, overlay))) return false
    try {
      for (const edit of editsOf(command)) {
        version = (await Effect.runPromise(svc.recordOperation(candidateId(), version, edit))).version
      }
      savedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      onRecorded()
      return true
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
      return false
    }
  }

  return { ...editing, open, propose, savedAt }
}
