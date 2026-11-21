/**
 * What the lines of the lab's picture break: each relation's breaches of the rules, by tier.
 *
 * Asked of the rules as they are stated, not restated: the readability rules and their tiers come from
 * `routeQuality` (`RULE_TIERS`), staying attached from `attachment`. Hard: a line through text, a bend
 * at a decorated end, a run along another line or a border, a line through another element (I5), a
 * line no route reaches, two connected elements over each other. Soft: a jog. The two other soft rules
 * — heads together, a label obscured — have no browser mirror yet, so the lab does not count them.
 */
import type { Extent, Point } from '../geometry'
import { elementsCrossed, endsConflict } from '../attachment'
import { RULE_TIERS, bendsAtEnds, kinks, runsAlong, textsCrossed } from '../routeQuality'
import type { Tier } from '../routeQuality'
import type { LabGeometry } from './labGeometry'
import type { Placement } from './labRouting'

export type Rule =
  | 'text'
  | 'bend-at-an-end'
  | 'runs-along'
  | 'jog'
  | 'crosses-an-element'
  | 'unroutable'
  | 'ends-overlap'

/** Staying attached is never given up, so every rule of it is hard. */
const ATTACHMENT_TIERS: Readonly<Record<'crosses-an-element' | 'unroutable' | 'ends-overlap', Tier>> = {
  'crosses-an-element': 'hard',
  unroutable: 'hard',
  'ends-overlap': 'hard',
}

export const tierOf = (rule: Rule): Tier =>
  rule in ATTACHMENT_TIERS
    ? ATTACHMENT_TIERS[rule as keyof typeof ATTACHMENT_TIERS]
    : (RULE_TIERS[rule] ?? 'hard')

export interface Breach {
  /** The relation's place on the picture. */
  readonly relation: number
  readonly rule: Rule
  readonly tier: Tier
  /** Where to mark it: the stretch of line that breaks it, or the whole line. */
  readonly at: readonly Point[]
}

const breach = (relation: number, rule: Rule, at: readonly Point[]): Breach =>
  ({ relation, rule, tier: tierOf(rule), at })

const segment = (course: readonly Point[], index: number): Point[] => [course[index], course[index + 1]]

/** Every breach of every relation, given each relation's course now (by its place) and where shapes are. */
export const breachesOf = (
  geometry: LabGeometry,
  placement: Placement,
  courses: ReadonlyMap<number, readonly Point[]>,
  text: ReadonlyMap<string, Extent>,
  unroutable: ReadonlySet<number> = new Set(),
): Breach[] => {
  const extents = new Map([...placement.elements, ...placement.boxes])
  const borders = [...extents.values()]
  return geometry.relations.flatMap((relation): Breach[] => {
    const source = extents.get(relation.source)
    const target = extents.get(relation.target)
    const conflict = source && target && endsConflict(source, target)
      ? [breach(relation.index, 'ends-overlap', [])]
      : []
    const course = courses.get(relation.index)
    if (unroutable.has(relation.index) || !course) return [...conflict, breach(relation.index, 'unroutable', [])]
    const others = [...courses].filter(([index]) => index !== relation.index).map(([, other]) => other)
    return [
      ...conflict,
      ...textsCrossed(course, text).map(() => breach(relation.index, 'text', course)),
      ...bendsAtEnds(course, relation.decorated).map((end) =>
        breach(relation.index, 'bend-at-an-end', end === 'A:source' ? course.slice(0, 2) : course.slice(-2))),
      ...runsAlong(course, others, borders).map((index) => breach(relation.index, 'runs-along', segment(course, index))),
      ...kinks(course).map((index) => breach(relation.index, 'jog', segment(course, index))),
      ...elementsCrossed(course, placement.elements, [relation.source, relation.target]).map(() =>
        breach(relation.index, 'crosses-an-element', course)),
    ]
  })
}

/** How many breaches there are of each tier. */
export const countByTier = (breaches: readonly Breach[]): Readonly<Record<Tier, number>> => ({
  hard: breaches.filter((one) => one.tier === 'hard').length,
  soft: breaches.filter((one) => one.tier === 'soft').length,
})
