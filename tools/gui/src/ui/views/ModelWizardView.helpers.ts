// Pure helpers for the guided modeling wizard's hub shell — unit-testable without a DOM.
import { domainOptionsForModules, getDomainColor } from '../lib/domains'
import { SPINE, DOMAIN_INTROS } from '../lib/wizardQuestionnaires'

export interface WizardDomainCard {
  readonly key: string
  readonly label: string
  readonly color: string
  readonly intro: string
  readonly createdCount: number
  /** True on the one card the spine recommends working on next ("Start here" / "Next"). */
  readonly recommended: boolean
}

type ModuleLike = { readonly name: string }

/**
 * Omnidirectional "model this next" recommendation (decision D-7 — no mode toggle):
 * - Fresh session (no spine domain touched): motivation, the classic "start from why" default —
 *   but only a default; starting anywhere is legitimate.
 * - Otherwise: an untouched spine neighbor of `lastDomain` (where the user just worked), so
 *   someone who started at application is pointed to common, someone who started at motivation
 *   to business. Forward neighbor (toward application) wins when both are untouched.
 * - Fallback: first untouched spine domain in order; null once the whole spine has content.
 */
export const recommendedNextDomain = (
  createdCounts: Record<string, number>,
  lastDomain?: string | null,
): string | null => {
  const untouched = (domain: string) => (createdCounts[domain] ?? 0) === 0
  if (SPINE.every(untouched)) return 'motivation'
  const at = lastDomain ? SPINE.indexOf(lastDomain) : -1
  if (at !== -1) {
    for (const neighbor of [SPINE[at + 1], SPINE[at - 1]]) {
      if (neighbor !== undefined && untouched(neighbor)) return neighbor
    }
  }
  return SPINE.find(untouched) ?? null
}

/** v1 scope is ArchiMate-only (WU-B2's "guided ArchiMate modeling wizard") — SysML excluded. */
export const buildWizardDomainCards = (
  createdCounts: Record<string, number>,
  lastDomain?: string | null,
  modules?: readonly ModuleLike[],
): WizardDomainCard[] => {
  const recommended = recommendedNextDomain(createdCounts, lastDomain)
  return domainOptionsForModules(modules)
    .map((option) => ({
      key: option.key,
      label: option.label,
      color: getDomainColor(option.key),
      intro: DOMAIN_INTROS[option.key] ?? '',
      createdCount: createdCounts[option.key] ?? 0,
      recommended: option.key === recommended,
    }))
}
