/**
 * What the lines of the canvas's picture break: each relation's breaches of the rules, by tier.
 *
 * Asked of the rules as they are stated, not restated: the readability rules and their tiers come from
 * `routeQuality` (`RULE_TIERS`), staying attached from `attachment`. Hard: a line through text, a bend
 * at a decorated end, a run along another line or a border, a line through another element (I5), a
 * line no route reaches, two connected elements over each other. Soft: a jog. The two other soft rules
 * — heads together, a label obscured — have no browser mirror yet, so the canvas does not count them.
 */
import type { Extent, Point } from './geometry'
import { elementsCrossed, endsConflict } from './attachment'
import { RULE_TIERS, bendsAtEnds, kinks, runIndex, runsAlongIn, textsCrossed } from './routeQuality'
import type { Tier } from './routeQuality'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import type { Placement } from './canvasRouting'

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
  geometry: LayoutGeometry,
  placement: Placement,
  courses: ReadonlyMap<number, readonly Point[]>,
  text: ReadonlyMap<string, Extent>,
  unroutable: ReadonlySet<number> = new Set(),
): Breach[] => {
  const extents = new Map([...placement.elements, ...placement.boxes])
  const runs = runIndex(courses, [...extents.values()])
  return geometry.relations.flatMap((relation): Breach[] => {
    const source = extents.get(relation.source)
    const target = extents.get(relation.target)
    const conflict = source && target && endsConflict(source, target)
      ? [breach(relation.index, 'ends-overlap', [])]
      : []
    const course = courses.get(relation.index)
    if (unroutable.has(relation.index) || !course) return [...conflict, breach(relation.index, 'unroutable', [])]
    return [
      ...conflict,
      ...textsCrossed(course, text).map(() => breach(relation.index, 'text', course)),
      ...bendsAtEnds(course, relation.decorated).map((end) =>
        breach(relation.index, 'bend-at-an-end', end === 'A:source' ? course.slice(0, 2) : course.slice(-2))),
      ...runsAlongIn(course, runs, relation.index).map((index) =>
        breach(relation.index, 'runs-along', segment(course, index))),
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

/** Each rule in a reader's words, as a line breaking it is described. */
const RULE_WORDS: Readonly<Record<Rule, string>> = {
  text: 'runs through text',
  'bend-at-an-end': 'bends at a decorated end',
  'runs-along': 'runs along another line or a border',
  jog: 'jogs',
  'crosses-an-element': 'crosses an element it does not join',
  unroutable: 'has no route that keeps every rule',
  'ends-overlap': 'joins two elements drawn over each other',
}

const keyOf = (one: Breach): string =>
  `${one.relation}:${one.rule}:${one.at.map((point) => `${point.x},${point.y}`).join(' ')}`

/** The breaches a reader is shown: a rule broken twice over the same stretch of a line is one breach. */
export const distinctBreaches = (breaches: readonly Breach[]): { key: string; breach: Breach }[] =>
  [...new Map(breaches.map((one) => [keyOf(one), one])).entries()].map(([key, breach]) => ({ key, breach }))

/** A breach in a reader's words: the line, by the elements it joins, and the rule it breaks. */
export const breachSentence = (breach: Breach, geometry: LayoutGeometry | null): string => {
  const relation = geometry?.relations.find((one) => one.index === breach.relation)
  const named = (alias: string): string =>
    geometry?.elements.find((one) => one.alias === alias)?.label
    ?? geometry?.boxes.find((one) => one.alias === alias)?.label ?? alias
  const line = relation ? `${named(relation.source)} → ${named(relation.target)}` : 'A line'
  return `${line} ${RULE_WORDS[breach.rule]}`
}
