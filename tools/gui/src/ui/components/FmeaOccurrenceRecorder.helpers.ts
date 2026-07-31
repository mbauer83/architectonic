/**
 * What recording an occurrence judgement consists of, apart from the form that collects it.
 *
 * Occurrence is the only factor nobody can derive, so it is the one place a person's judgement
 * enters the matrix. Two rules hold throughout and are the reason this is separated out where they
 * can be asserted: the cited facts may pre-fill the rationale, and **nothing may pre-fill the
 * value**; and the submission always carries the basis digest, because a judgement filed without
 * one is retained and never applies, leaving the row undecidable however carefully it was judged.
 */
import type { CellView } from '../views/AssuranceFmeaView.helpers'
import { occurrenceBasisDigest } from '../views/AssuranceFmeaView.helpers'

export interface RecorderDraft {
  value: string
  justification: string
  author: string
}

export interface FactorRequestBody {
  factor: 'occurrence'
  value: string
  justification: string
  author: string
  basis_digest: string
}

/** The starting state of the form: the rationale seeded from the facts, and no value chosen.
 *
 * The empty value is the point. A selected member would read as the tool's opinion, and the
 * rationale beneath it as agreement with the tool rather than a judgement of its own. */
export function initialDraft(cell: CellView, rememberedAuthor: string): RecorderDraft {
  return { value: '', justification: cell.occurrence_rationale_draft, author: rememberedAuthor }
}

/** The cited facts as separate lines, for showing what the rationale was seeded from. */
export function citedFacts(draft: string): string[] {
  return draft
    .split('\n')
    .map((line) => line.replace(/^-\s*/, '').trim())
    .filter((line) => line.length > 0)
}

/** Whether the judgement can be sent: a value, a rationale, and someone accountable for it.
 *
 * All three are required by the backend for the same reason — a priority band with no attributable,
 * stated reason is the one that gets argued about in a review and cannot be defended. Checked here
 * too so the button is disabled rather than the submission rejected. */
export function isSubmittable(draft: RecorderDraft): boolean {
  return (
    draft.value !== ''
    && draft.justification.trim().length > 0
    && draft.author.trim().length > 0
  )
}

/** The judgement itself. No `node_id`: the failure mode is the address it is posted to. */
export function factorRequestBody(cell: CellView, draft: RecorderDraft): FactorRequestBody {
  return {
    factor: 'occurrence',
    value: draft.value,
    justification: draft.justification,
    author: draft.author.trim(),
    basis_digest: occurrenceBasisDigest(cell),
  }
}

/** What to tell the person when the judgement was not recorded.
 *
 * A locked store is named as such rather than reported as a failure, because it is a state they can
 * do something about; the backend's own field messages are preferred over any restatement here. */
export function recorderErrorMessage(
  status: number,
  body: { errors?: { message: string }[] } | null,
): string {
  if (status === 423) return 'The assurance store is locked. Unlock it and try again.'
  const stated = body?.errors?.map((e) => e.message).filter((m) => m.length > 0) ?? []
  if (stated.length) return stated.join('; ')
  return 'The judgement was not recorded.'
}
