/**
 * Integrating candidates as the Integration tab reads it (06·7, plan §3): each conflict the server answers,
 * what a party proposes in words, the resolution each action makes, and what each party answers in the
 * analysis — the adaptation that holds it, the end states it answers and the stressors behind them. The
 * conflicts, and what settles them, are the server's (`candidates_integrate_candidates`); nothing here judges.
 */
import type { DocumentTableRow, IntegrationConflict, Resolution, ResolutionAction } from '../schemas/candidates'
import { stableEntityId } from '../artifactId'
import { cell, cellIds } from '../stressAnalysis/analysisRows'
import { operationLabel } from './candidateApply'

const KINDS = ['same-key', 'remove-versus-use'] as const

/** The conflict's kind as a resolution names it; the server only answers these two. */
const kindOf = (conflict: IntegrationConflict): Resolution['kind'] =>
  KINDS.find((kind) => kind === conflict.kind) ?? 'same-key'

/** An element or a candidate by name; the id where there is none. */
export type NameOf = (id: string) => string

const text = (value: unknown): string => (typeof value === 'string' ? value : '')

/** *operation* with the elements it names written as their names, as a reader reads it. */
const named = (operation: Readonly<Record<string, unknown>>, nameOf: NameOf): Readonly<Record<string, unknown>> => ({
  ...operation,
  ...Object.fromEntries(['artifact_id', 'source_entity', 'target_entity']
    .filter((part) => text(operation[part])).map((part) => [part, nameOf(text(operation[part]))])),
})

/** What *conflict* is about, in a reader's words: what the parties change, by name. */
export const conflictSubject = (conflict: IntegrationConflict, nameOf: NameOf): string => {
  const first = named(conflict.parties[0]?.operation ?? {}, nameOf)
  const field = [text(first.field), text(first.key)].filter(Boolean).join('.')
  const what = text(first.artifact_id) || `${text(first.source_entity)} → ${text(first.target_entity)}`
  return field ? `the ${field} of ${what}` : what
}

/** The conflict as a heading: what kind of disagreement, about what. */
export const conflictTitle = (conflict: IntegrationConflict, nameOf: NameOf): string =>
  conflict.kind === 'same-key'
    ? `Both change ${conflictSubject(conflict, nameOf)}`
    : `One removes what another uses: ${conflictSubject(conflict, nameOf)}`

/** Whether *conflict* permits *action*. */
export const permits = (conflict: IntegrationConflict, action: ResolutionAction): boolean =>
  conflict.actions.includes(action)

/** What one party does, as a line naming the elements it is about; the value it writes is read beside it. */
export const proposalLabel = (operation: Readonly<Record<string, unknown>>, nameOf: NameOf): string =>
  operationLabel(named(operation, nameOf))

/** What one party proposes, as a line naming the elements it is about and the value it writes. */
export const proposal = (operation: Readonly<Record<string, unknown>>, nameOf: NameOf): string => {
  const value = operation.value
  const said = value === undefined ? '' : ` to ${typeof value === 'string' ? `“${value}”` : JSON.stringify(value)}`
  return `${proposalLabel(operation, nameOf)}${said}`
}

/** Taking *party*'s side, or dropping its operation, in *conflict*. */
export const partyResolution = (
  conflict: IntegrationConflict, action: 'take' | 'drop', party: string,
): Resolution => ({ kind: kindOf(conflict), subject: conflict.subject, action, party })

/** Writing *value* into the integration in place of the parties' values. */
export const mergedResolution = (conflict: IntegrationConflict, value: string): Resolution => ({
  kind: kindOf(conflict), subject: conflict.subject, action: 'merge', value,
})

/** A settled conflict in words: what was done, naming the candidate by *nameOf*, about what *about* says. */
export const resolutionWords = (resolution: Resolution, nameOf: NameOf, about: string): string => ({
  take: () => `Took the side of ${nameOf(resolution.party ?? '')} on ${about}`,
  drop: () => `Dropped the change of ${nameOf(resolution.party ?? '')} to ${about}`,
  merge: () => `Merged ${about} as “${String(resolution.value)}”`,
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
  conflict: IntegrationConflict, options: readonly DecisionOption[], nameOf: NameOf,
): { readonly title: string; readonly body: string } => ({
  title: `Decide ${conflictSubject(conflict, nameOf)}`,
  body: [
    '## Context',
    '',
    `Integrating ${options.map((one) => one.name).join(' and ')} found a conflict. ${conflictTitle(conflict, nameOf)}.`,
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
