/**
 * The diagram reader (B97): what a selection reaches along the relations a diagram draws, and the
 * reading written into and read back from the page's address.
 *
 * A reading is a selection, how far to follow what leads to it (*incoming*) and what it leads to
 * (*outgoing*), and the window it is looked at through. The reach is walked over the model direction
 * of each relation; a relation whose type has no direction (an association) leads both ways, so it is
 * followed by either walk.
 *
 * The address is a syntax this project both writes and reads back, so its writer and its reader live
 * here together and are tested as a pair:
 *
 *     focus=<stem>,<stem>&reach=in:<steps>,out:<steps>&view=<x>,<y>,<percent>
 *
 * `focus` names entities by their rename-stable stem (`stableEntityId`), so a link survives a rename.
 * The reading lens is not part of it: how a diagram is coloured is the reader's preference, what is
 * being read is the link's.
 */
import { stableEntityId } from './artifactId'

/** How many relations to follow from the selection: none, one, two, or until nothing new is reached. */
export type ReachSteps = 0 | 1 | 2 | 'all'
export const REACH_STEPS: readonly ReachSteps[] = [0, 1, 2, 'all']

export interface Reach {
  readonly incoming: ReachSteps
  readonly outgoing: ReachSteps
}

/** One step each way: what a fresh selection reads. */
export const DEFAULT_REACH: Reach = { incoming: 1, outgoing: 1 }

/** A relation as the reach walks it: its ends, and whether its type has a direction. */
export interface ReadingRelation {
  readonly id: string
  readonly source: string
  readonly target: string
  readonly directed: boolean
}

/** What a selection reaches, each list in the order it was reached, without the selection itself. */
export interface ReachResult {
  readonly incoming: readonly string[]
  readonly outgoing: readonly string[]
  /** Every relation a walk crossed: the ones the picture keeps at full strength. */
  readonly relations: ReadonlySet<string>
}

const stepsOf = (steps: ReachSteps): number => (steps === 'all' ? Number.POSITIVE_INFINITY : steps)

/** The far end of *relation* when walked from *from*, in the walk's direction; null when it does not lead there. */
const farEnd = (relation: ReadingRelation, from: string, walk: 'incoming' | 'outgoing'): string | null => {
  const [near, far] = walk === 'outgoing' ? [relation.source, relation.target] : [relation.target, relation.source]
  if (near === from) return far
  if (!relation.directed && far === from) return near
  return null
}

const walk = (
  selection: ReadonlySet<string>, relations: readonly ReadingRelation[], steps: ReachSteps,
  direction: 'incoming' | 'outgoing', crossed: Set<string>,
): string[] => {
  const reached: string[] = []
  const seen = new Set(selection)
  let frontier = [...selection]
  for (let step = 0; step < stepsOf(steps) && frontier.length > 0; step += 1) {
    const next: string[] = []
    for (const from of frontier) {
      for (const relation of relations) {
        const to = farEnd(relation, from, direction)
        if (to === null) continue
        crossed.add(relation.id)
        if (seen.has(to)) continue
        seen.add(to)
        reached.push(to)
        next.push(to)
      }
    }
    frontier = next
  }
  return reached
}

/** What *selection* reaches along *relations*, walked incoming and outgoing as far as *reach* says. */
export const reachOf = (
  selection: readonly string[], relations: readonly ReadingRelation[], reach: Reach,
): ReachResult => {
  const start = new Set(selection)
  const crossed = new Set<string>()
  return {
    incoming: walk(start, relations, reach.incoming, 'incoming', crossed),
    outgoing: walk(start, relations, reach.outgoing, 'outgoing', crossed),
    relations: crossed,
  }
}

/** Where the window is: the centre of the picture it shows, in the picture's units, and the zoom in percent. */
export interface ReadingView {
  readonly x: number
  readonly y: number
  readonly percent: number
}

/** A reading as the address carries it. `focus` holds stems; the page resolves them against what it draws. */
export interface AddressedReading {
  readonly focus: readonly string[]
  readonly reach: Reach
  readonly view: ReadingView | null
}

/** The address's query parameters for a reading. An empty selection writes no `focus` and no `reach`. */
export const readingQuery = (reading: AddressedReading): Record<string, string> => {
  const query: Record<string, string> = {}
  if (reading.focus.length > 0) {
    query.focus = reading.focus.map(stableEntityId).join(',')
    query.reach = `in:${reading.reach.incoming},out:${reading.reach.outgoing}`
  }
  if (reading.view) {
    const { x, y, percent } = reading.view
    query.view = `${Math.round(x)},${Math.round(y)},${Math.round(percent)}`
  }
  return query
}

const stepsFrom = (text: string | undefined): ReachSteps | null => {
  if (text === 'all') return 'all'
  const number = Number(text)
  return number === 0 || number === 1 || number === 2 ? number : null
}

const reachFrom = (text: string): Reach => {
  const parts = new Map(text.split(',').map((part) => part.split(':') as [string, string | undefined]))
  return {
    incoming: stepsFrom(parts.get('in')) ?? DEFAULT_REACH.incoming,
    outgoing: stepsFrom(parts.get('out')) ?? DEFAULT_REACH.outgoing,
  }
}

const viewFrom = (text: string): ReadingView | null => {
  const numbers = text.split(',').map(Number)
  if (numbers.length !== 3 || numbers.some((number) => !Number.isFinite(number))) return null
  const [x, y, percent] = numbers
  return percent > 0 ? { x, y, percent } : null
}

const single = (value: unknown): string | undefined => {
  const first: unknown = Array.isArray(value) ? (value as unknown[])[0] : value
  return typeof first === 'string' ? first : undefined
}

/**
 * The reading an address carries. Tolerant, because a link is typed and pasted by people: a part it
 * cannot read is left at its default rather than refusing the whole reading.
 */
export const readingFromQuery = (query: Readonly<Record<string, unknown>>): AddressedReading => {
  const focus = single(query.focus)
  const reach = single(query.reach)
  const view = single(query.view)
  return {
    focus: focus ? focus.split(',').map((id) => id.trim()).filter((id) => id !== '') : [],
    reach: reach ? reachFrom(reach) : DEFAULT_REACH,
    view: view ? viewFrom(view) : null,
  }
}

/** The ids among *drawn* that the address's stems name, in the address's order. */
export const resolveFocus = (stems: readonly string[], drawn: readonly string[]): string[] => {
  const byStem = new Map(drawn.map((id) => [stableEntityId(id), id]))
  return stems.flatMap((stem) => {
    const id = byStem.get(stableEntityId(stem))
    return id ? [id] : []
  })
}
