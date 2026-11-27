/**
 * A diagram's own purpose line while it is edited: seeded from the read, sent back whole on save.
 *
 * Both lists are always sent, so a list emptied here is cleared on the server — the diagram then shows
 * its viewpoint's, which the detail page says. The names of referenced elements come from the read's
 * shown line, so a stored reference shows its element's name rather than its id.
 */
import { reactive } from 'vue'
import type { DiagramDetail } from '../../domain'
import type { PurposeEntry } from '../../domain/purposeLines'

interface PurposeDraftState {
  stakeholders: PurposeEntry[]
  concerns: PurposeEntry[]
  names: Record<string, string>
}

export function useDiagramPurposeDraft() {
  const state = reactive<PurposeDraftState>({ stakeholders: [], concerns: [], names: {} })

  const seed = (detail: DiagramDetail) => {
    state.stakeholders = [...(detail.stakeholders ?? [])]
    state.concerns = [...(detail.concerns ?? [])]
    const shown = [...(detail.purpose?.stakeholders ?? []), ...(detail.purpose?.concerns ?? [])]
    state.names = Object.fromEntries(shown.flatMap((entry) => (entry.ref ? [[entry.ref, entry.text]] : [])))
  }

  const forWrite = () => ({ stakeholders: [...state.stakeholders], concerns: [...state.concerns] })

  return { state, seed, forWrite }
}
