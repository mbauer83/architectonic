/**
 * The entity page's advice, as pure values: what an acknowledgement edit sends, and how a count reads.
 *
 * How prominently advice is shown is not decided here — the server sends `presentation` from the
 * element's status, so the policy has one statement. What is decided here is only what the page's own
 * actions write: an acknowledgement replaces the stored set, so the set sent is the stored one with
 * the new entry put in, or the withdrawn one taken out.
 */

import type { AcceptedAdviceReading } from '../../domain/schemas/entities'

export interface AcceptedAdviceEntry {
  readonly code: string
  readonly reason: string
}

const stored = (accepted: readonly AcceptedAdviceReading[]): AcceptedAdviceEntry[] =>
  accepted.map(({ code, reason }) => ({ code, reason }))

/** The stored acknowledgements with *code* accepted for *reason* — replacing an earlier one for it. */
export const acknowledging = (
  accepted: readonly AcceptedAdviceReading[],
  code: string,
  reason: string,
): AcceptedAdviceEntry[] => [...stored(accepted).filter((entry) => entry.code !== code), { code, reason: reason.trim() }]

/** The stored acknowledgements without the one for *code*: the advice speaks again. */
export const withdrawing = (accepted: readonly AcceptedAdviceReading[], code: string): AcceptedAdviceEntry[] =>
  stored(accepted).filter((entry) => entry.code !== code)

/** The marker's text: a count, never the findings themselves. */
export const adviceCountLabel = (count: number): string => (count === 1 ? '1 advice' : `${count} advice`)

/** Whether there is a reason to send. How long one may be is the server's rule, and its refusal says so. */
export const hasAReason = (reason: string): boolean => reason.trim().length > 0
