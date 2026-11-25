/**
 * The perspectives a stressor can be thought of from, as the stressor input offers them: which have
 * no stressor yet, once kinds are in use, and one chosen at random. The frameworks are the server's.
 */
import type { PerspectiveFramework, StressPerspective } from '../schemas/stressEvaluation'

/**
 * The perspectives no stressor is written from yet, by id. Empty while no stressor names a kind: the
 * kind is optional, so an empty column says nothing about coverage.
 */
export const unwritten = (
  frameworks: readonly PerspectiveFramework[], kinds: readonly string[],
): ReadonlySet<string> => {
  const used = new Set(kinds.map((kind) => kind.trim().toLowerCase()).filter(Boolean))
  return used.size === 0
    ? new Set()
    : new Set(frameworks.flatMap((one) => one.perspectives).filter((one) => !used.has(one.kind)).map((one) => one.id))
}

/** One perspective of any framework, chosen by *pick* (a number in [0, 1)); none where there are none. */
export const randomPerspective = (
  frameworks: readonly PerspectiveFramework[], pick: number,
): { readonly framework: string; readonly perspective: StressPerspective } | null => {
  const all = frameworks.flatMap((framework) => framework.perspectives.map((perspective) => ({
    framework: framework.id, perspective,
  })))
  return all[Math.min(Math.floor(pick * all.length), all.length - 1)] ?? null
}
