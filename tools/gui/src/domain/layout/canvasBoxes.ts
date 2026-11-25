/**
 * A diagram's boxes edited on its canvas (D9, A-02.39): renamed, deleted, a type box added inside a box,
 * and every layer and type box given back to the renderer ("Return to automatic boxes").
 *
 * A diagram that states no ruled grouping draws its layer and type boxes automatically. The first edit
 * of one writes them all down as ruled groupings — read off the picture, which says what each computed
 * box admits (`rule`) and which box it sits in (`inside`) — and then owns them: the same
 * harvest-then-own as the layout's takeover. Returning to automatic boxes drops every ruled grouping
 * again; the diagram's listed groupings stay.
 *
 * A box is found among the groupings by its grouping id where the picture gives it one, and otherwise
 * by the labels of the boxes it sits in, outermost first — which is how a box written down in this
 * session, and not yet given an id by a save, is told apart from its siblings.
 */
import { type AuthoredGrouping, withoutEmptyGroups } from '../authoredGrouping'
import { stableEntityId } from '../artifactId'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'

type Box = LayoutGeometry['boxes'][number]

/** The kinds of box a grouping draws: computed layer and type boxes, and those a diagram states. */
const GROUPING_KINDS: ReadonlySet<Box['kind']> = new Set(['domain', 'type', 'authored-grouping'])

/** Whether *box* is one of the diagram's boxes, rather than an element drawn with its parts inside. */
export const isGroupingBox = (box: Box): boolean => GROUPING_KINDS.has(box.kind)

/** Whether *groupings* state any ruled grouping, at any depth: the boxes are then the diagram's own. */
export const statesRuledBoxes = (groupings: readonly AuthoredGrouping[]): boolean =>
  groupings.some((one) => one.rule !== undefined || statesRuledBoxes(one.groups ?? []))

/** The boxes of *picture* the renderer computed, as the ruled groupings that draw them, nested as drawn. */
export const harvestedBoxes = (picture: LayoutGeometry): AuthoredGrouping[] => {
  const computed = picture.boxes.filter((box) => box.rule !== undefined)
  const within = (outer: string | undefined): AuthoredGrouping[] => {
    const seen = new Set<string>()
    return computed.filter((box) => (box.inside ?? undefined) === outer || (outer === undefined
      && !computed.some((one) => one.alias === box.inside)))
      .flatMap((box) => {
        // A type the renderer boxed once per flow is one ruled grouping: its rule selects them all.
        const rule = Object.entries(box.rule ?? {}).map(([kind, value]) => `${kind}:${value}`).join()
        if (seen.has(rule)) return []
        seen.add(rule)
        const groups = within(box.alias)
        return [{ label: box.label, 'entity-ids': [], rule: { ...box.rule }, ...(groups.length ? { groups } : {}) }]
      })
  }
  return within(undefined)
}

/** The groupings a box edit starts from: the session's, with the computed boxes written down if none is. */
export const ownedBoxes = (
  groupings: readonly AuthoredGrouping[], picture: LayoutGeometry,
): readonly AuthoredGrouping[] => (statesRuledBoxes(groupings) ? groupings : [...groupings, ...harvestedBoxes(picture)])

/** The labels of the boxes *alias* sits in on *picture*, outermost first, ending with its own. */
const labelTrail = (picture: LayoutGeometry, alias: string): readonly string[] => {
  const byAlias = new Map(picture.boxes.map((box) => [box.alias, box]))
  const trail: string[] = []
  for (let box = byAlias.get(alias); box && trail.length < byAlias.size; box = byAlias.get(box.inside ?? '')) {
    if (isGroupingBox(box)) trail.unshift(box.label)
  }
  return trail
}

/** Where a grouping sits: the indexes from the top, one per level. */
export type Trail = readonly number[]

const findTrail = (
  groupings: readonly AuthoredGrouping[], wanted: (one: AuthoredGrouping) => boolean,
): Trail | null => {
  for (const [index, one] of groupings.entries()) {
    if (wanted(one)) return [index]
    const below = findTrail(one.groups ?? [], wanted)
    if (below) return [index, ...below]
  }
  return null
}

/** Where *alias*'s box sits among *groupings*: by its id, else by the labels of the boxes round it. */
export const trailOf = (
  groupings: readonly AuthoredGrouping[], picture: LayoutGeometry, alias: string,
): Trail | null => {
  const key = picture.boxes.find((box) => box.alias === alias)?.key
  const byId = key === undefined ? null : findTrail(groupings, (one) => one.id === key)
  if (byId) return byId
  const labels = labelTrail(picture, alias)
  const walk = (level: readonly AuthoredGrouping[], depth: number): Trail | null => {
    const at = level.findIndex((one) => one.label === labels[depth])
    if (at < 0) return null
    if (depth === labels.length - 1) return [at]
    const below = walk(level[at].groups ?? [], depth + 1)
    return below && [at, ...below]
  }
  return labels.length ? walk(groupings, 0) : null
}

/** The grouping at *trail*; undefined where none is. */
export const groupingAt = (groupings: readonly AuthoredGrouping[], trail: Trail): AuthoredGrouping | undefined => {
  const [index, ...rest] = trail
  const one = index === undefined ? undefined : groupings[index]
  return rest.length === 0 || one === undefined ? one : groupingAt(one.groups ?? [], rest)
}

/** *groupings* with the level at *trail* replaced by what *change* makes of it. */
const atLevel = (
  groupings: readonly AuthoredGrouping[], trail: Trail,
  change: (level: readonly AuthoredGrouping[], index: number) => readonly AuthoredGrouping[],
): AuthoredGrouping[] => {
  const [index, ...rest] = trail
  if (rest.length === 0) return [...change(groupings, index)]
  return groupings.map((one, at) => (at === index ? { ...one, groups: atLevel(one.groups ?? [], rest, change) } : one))
}

/** The box at *trail* called *label*. */
export const renamedBox = (groupings: readonly AuthoredGrouping[], trail: Trail, label: string): AuthoredGrouping[] =>
  atLevel(groupings, trail, (level, index) => level.map((one, at) => (at === index ? { ...one, label } : one)))

/**
 * The box at *trail* gone from the diagram, never anything it holds: its boxes take its place, and the
 * elements it lists join the box around it (a ruled box lists none; its elements go where a rule or a
 * box admits them next).
 */
export const withoutBox = (groupings: readonly AuthoredGrouping[], trail: Trail): AuthoredGrouping[] => {
  const gone = groupingAt(groupings, trail)
  const lifted = atLevel(groupings, trail, (level, index) => [
    ...level.slice(0, index), ...(level[index].groups ?? []), ...level.slice(index + 1),
  ])
  const listed = gone?.['entity-ids'] ?? []
  if (trail.length < 2 || listed.length === 0) return lifted
  return atLevel(lifted, trail.slice(0, -1), (level, index) => level.map((one, at) => (at === index
    ? { ...one, 'entity-ids': [...one['entity-ids'], ...listed] } : one)))
}

/** A box of the elements of *type* inside the box at *trail*, labelled *label*. */
export const withTypeBox = (
  groupings: readonly AuthoredGrouping[], trail: Trail, type: string, label: string,
): AuthoredGrouping[] => atLevel(groupings, trail, (level, index) => level.map((one, at) => (at === index
  ? { ...one, groups: [...one.groups ?? [], { label, 'entity-ids': [], rule: { type } }] } : one)))

/** Each box of *groupings*, by what it is the same box by: its id, else its rule or label within its parent. */
const boxesOf = (groupings: readonly AuthoredGrouping[], parent = ''): readonly (readonly [string, string])[] =>
  groupings.flatMap((one) => {
    const self = one.id ?? `${parent}/${one.rule ? Object.entries(one.rule).join('=') : `"${one.label}"`}`
    return [[self, one.label] as const, ...boxesOf(one.groups ?? [], self)]
  })

/**
 * What a session changed in the diagram's boxes, as rows of the list Save shows: *stated* is what the
 * diagram states, *now* what the session holds, *picture* the picture last saved, whose computed boxes
 * count as the diagram's own once any box is written down.
 */
export const boxChanges = (
  stated: readonly AuthoredGrouping[], now: readonly AuthoredGrouping[], picture: LayoutGeometry | undefined,
): readonly { readonly key: string; readonly text: string }[] => {
  if (statesRuledBoxes(stated) && !statesRuledBoxes(now)) {
    return [{ key: 'boxes:automatic', text: 'Returned to automatic boxes' }]
  }
  const before = new Map(boxesOf(statesRuledBoxes(now) && picture ? ownedBoxes(stated, picture) : stated))
  const after = new Map(boxesOf(now))
  return [
    ...[...after].filter(([self]) => !before.has(self))
      .map(([self, label]) => ({ key: `box+${self}`, text: `Box added: ${label}` })),
    ...[...after].flatMap(([self, label]) => {
      const was = before.get(self)
      return was !== undefined && was !== label ? [{ key: `box~${self}`, text: `Box renamed: ${was} → ${label}` }] : []
    }),
    ...[...before].filter(([self]) => !after.has(self))
      .map(([self, label]) => ({
        key: `box-${self}`, text: `Box deleted: ${label} — what it held stays on the diagram`,
      })),
  ]
}

/**
 * A new listed box labelled *label* round the drawings *keys*, at the top of the diagram. A drawing sits in
 * one listed box only, so each leaves the listed box it was in; a box left empty goes with it.
 */
export const withNewBox = (
  groupings: readonly AuthoredGrouping[], keys: readonly string[], label: string,
): AuthoredGrouping[] => {
  const moving = new Set(keys.map(stableEntityId))
  const withdrawn = (level: readonly AuthoredGrouping[]): AuthoredGrouping[] => level.map((one) => ({
    ...one, 'entity-ids': one['entity-ids'].filter((id) => !moving.has(stableEntityId(id))),
    ...(one.groups ? { groups: withdrawn(one.groups) } : {}),
  }))
  return [...withoutEmptyGroups(withdrawn(groupings)), { label, 'entity-ids': [...keys] }]
}

/** *groupings* with every ruled grouping dropped, its boxes taking its place: the renderer's boxes again. */
export const withoutRuledBoxes = (groupings: readonly AuthoredGrouping[]): AuthoredGrouping[] =>
  groupings.flatMap((one) => {
    const groups = withoutRuledBoxes(one.groups ?? [])
    if (one.rule !== undefined) return groups
    return [{ ...one, ...(one.groups ? { groups } : {}) }]
  })
