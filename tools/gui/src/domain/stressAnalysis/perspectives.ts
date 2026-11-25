/**
 * The perspectives a stressor can be thought of from, as the stressor input offers them: one chosen at
 * random. The frameworks, and which have no stressor yet, are the server's.
 */
import type { PerspectiveFramework, StressPerspective } from '../schemas/stressEvaluation'

/** One perspective of any framework, chosen by *pick* (a number in [0, 1)); none where there are none. */
export const randomPerspective = (
  frameworks: readonly PerspectiveFramework[], pick: number,
): { readonly framework: string; readonly perspective: StressPerspective } | null => {
  const all = frameworks.flatMap((framework) => framework.perspectives.map((perspective) => ({
    framework: framework.id, perspective,
  })))
  return all[Math.min(Math.floor(pick * all.length), all.length - 1)] ?? null
}
