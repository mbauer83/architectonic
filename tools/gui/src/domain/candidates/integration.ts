/**
 * Integrating candidates as the Integration tab reads it (06·7, plan §3): each conflict the server answers,
 * what a party proposes in words, the resolution each action makes, and what each party answers in the
 * analysis — the adaptation that holds it, the end states it answers and the stressors behind them. The
 * conflicts, and what settles them, are the server's (`changes_integrate_candidates`); nothing here judges.
 */
import type { DocumentTableRow, IntegrationConflict, Resolution, ResolutionAction } from '../schemas/candidates'
import { stableEntityId } from '../artifactId'
import { cell, cellIds } from '../stressAnalysis/analysisRows'
import { operationLabel } from './candidateApply'

const KINDS = ['same-key', 'remove-versus-use'] as const

/** The conflict's kind as a resolution names it; the server only answers these two. */
const kindOf = (conflict: IntegrationConflict): Resolution['kind'] =>
  KINDS.find((kind) => kind === conflict.kind) ?? 'same-key'

/** What *conflict* is about, in a reader's words. */
export const conflictTitle = (conflict: IntegrationConflict): string =>
  conflict.kind === 'same-key' ? `Both change ${conflict.subject}` : `One removes what another uses: ${conflict.subject}`

/** Whether *conflict* permits *action*. */
export const permits = (conflict: IntegrationConflict, action: ResolutionAction): boolean =>
  conflict.actions.includes(action)

/** What one party proposes, as a line. */
export const proposal = (operation: Readonly<Record<string, unknown>>): string => {
  const value = operation.value
  const said = value === undefined ? '' : ` to ${typeof value === 'string' ? `“${value}”` : JSON.stringify(value)}`
  return `${operationLabel(operation)}${said}`
}

/** Taking *party*'s side, or dropping its operation, in *conflict*. */
export const partyResolution = (
  conflict: IntegrationConflict, action: 'take' | 'drop', party: string,
): Resolution => ({ kind: kindOf(conflict), subject: conflict.subject, action, party })

/** Writing *value* into the integration in place of the parties' values. */
export const mergedResolution = (conflict: IntegrationConflict, value: string): Resolution => ({
  kind: kindOf(conflict), subject: conflict.subject, action: 'merge', value,
})

/** A settled conflict in words, naming the candidate by *nameOf*. */
export const resolutionWords = (resolution: Resolution, nameOf: (id: string) => string): string => ({
  take: () => `Took ${nameOf(resolution.party ?? '')}'s side on ${resolution.subject}`,
  drop: () => `Dropped ${nameOf(resolution.party ?? '')}'s change to ${resolution.subject}`,
  merge: () => `Merged ${resolution.subject} as “${String(resolution.value)}”`,
})[resolution.action]()

/** What a candidate answers in an analysis: the end states its adaptation rows name, and their stressors. */
export interface AnswerLinks {
  readonly adaptations: readonly string[]
  readonly endStates: readonly string[]
  readonly stressors: readonly string[]
}

/** The adaptation rows holding *candidate*, the end states they answer, and the design stressors behind them. */
export const answerLinks = (
  candidate: string, adaptations: readonly DocumentTableRow[], stressors: readonly DocumentTableRow[],
): AnswerLinks => {
  const holding = adaptations
    .filter((row) => stableEntityId(cell(row, 'candidate_architecture')) === stableEntityId(candidate))
  const endStates = [...new Set(holding.flatMap((row) => cellIds(row, 'end_states')))]
  return {
    adaptations: holding.map((row) => row.row_id),
    endStates,
    stressors: stressors.filter((row) => endStates.includes(cell(row, 'end_state'))).map((row) => row.row_id),
  }
}

/** One option of a decision raised about a conflict: a party, what it proposes, and what it answers. */
export interface DecisionOption {
  readonly name: string
  readonly proposes: string
  readonly answers: readonly string[]
}

/**
 * The draft ADR a raised decision opens with: the conflict as its context, each party's proposal as an
 * option, and the decision and its consequences left to the author. Nothing here accepts it.
 */
export const decisionDraft = (
  conflict: IntegrationConflict, options: readonly DecisionOption[],
): { readonly title: string; readonly body: string } => ({
  title: `Decide: ${conflict.subject}`,
  body: [
    '## Context',
    '',
    `Integrating ${options.map((one) => one.name).join(' and ')} found a conflict. ${conflictTitle(conflict)}.`,
    'No merge proves behaviour; the options are what each candidate proposes.',
    '',
    '## Decision',
    '',
    'To be decided. The options:',
    '',
    ...options.map((one) => `- **${one.name}**: ${one.proposes}${
      one.answers.length ? ` (answers ${one.answers.join(', ')})` : ''}`),
    '',
    '## Consequences',
    '',
    'To be stated once decided.',
  ].join('\n'),
})
