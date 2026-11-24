/**
 * The element types one may add at a point on a diagram (sketch 03·2, second pass): every type the
 * diagram type accepts, in the catalogue's own order — first the ones used recently in this browser,
 * then the ones already on this diagram, then the rest under their framework and layer. One list, a
 * filter narrowing it as one types. The layer's colour is the ontology's (`ui/lib/domains`), never here.
 */
import { FRAMEWORK_GROUPS, getDomainLabel } from '../lib/domains'

export interface TypeRow {
  readonly type: string
  readonly domain: string
}

export interface TypeSection {
  readonly key: string
  readonly title: string
  /** A muted note after the title: "in this browser". */
  readonly note?: string
  /** The framework a run of layers belongs to, said once above its first layer. */
  readonly framework?: string
  /** The layer the section is, coloured as the ontology colours it. */
  readonly domain?: string
  readonly items: readonly TypeRow[]
}

/** How a type reads: `business-object` and `businessObject` both read "business object". */
export const typeWords = (type: string): string =>
  type.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[-_]+/g, ' ').toLowerCase()

const frameworkOf = (domain: string): string | undefined =>
  FRAMEWORK_GROUPS.find((group) => (group.domains as readonly string[]).includes(domain))?.label

/**
 * The sections of *palette* (the diagram type's types, in catalogue order): *recent* first, then the
 * types *inDiagram* draws, then each layer of what is left. A *filter* keeps the types whose words hold
 * it and drops the sections it empties, and the framework headings with them.
 */
export const typeSections = (
  palette: readonly TypeRow[], inDiagram: Iterable<string>, recent: readonly string[], filter = '',
): readonly TypeSection[] => {
  const wanted = filter.trim().toLowerCase()
  const rows = palette.filter((row) => !wanted || typeWords(row.type).includes(wanted))
  const byType = new Map(rows.map((row) => [row.type, row]))
  const recentRows = recent.flatMap((type) => byType.get(type) ?? [])
  const drawn = new Set(inDiagram)
  const recentTypes = new Set(recentRows.map((row) => row.type))
  const here = rows.filter((row) => drawn.has(row.type) && !recentTypes.has(row.type))
  const placed = new Set([...recentTypes, ...here.map((row) => row.type)])
  const rest = rows.filter((row) => !placed.has(row.type))
  const layers = [...new Set(rest.map((row) => row.domain))]
  let framework: string | undefined
  const layered = layers.map((domain): TypeSection => {
    const said = frameworkOf(domain)
    const first = said !== undefined && said !== framework
    framework = said
    return {
      key: `domain:${domain}`, title: getDomainLabel(domain), domain,
      framework: first && !wanted ? said : undefined,
      items: rest.filter((row) => row.domain === domain),
    }
  })
  return [
    { key: 'recent', title: 'Recently used', note: 'in this browser', items: recentRows },
    { key: 'here', title: 'In this diagram', items: here },
    ...layered,
  ].filter((section) => section.items.length > 0)
}

/** Where this browser keeps the types it used last; the key the canvas has always used. */
export const RECENT_TYPES_KEY = 'diagram-recent-model-types'
/** How many recent types the list offers. */
export const RECENT_TYPES_SHOWN = 5

type Store = Pick<Storage, 'getItem' | 'setItem'>
const browserStore = (): Store | null => {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

/** The types used last in this browser, newest first; none where storage is blocked or holds nonsense. */
export const recentTypes = (store: Store | null = browserStore()): string[] => {
  try {
    const stored: unknown = JSON.parse(store?.getItem(RECENT_TYPES_KEY) ?? '[]')
    return Array.isArray(stored)
      ? stored.filter((one): one is string => typeof one === 'string').slice(0, RECENT_TYPES_SHOWN)
      : []
  } catch {
    return []
  }
}

/** Note *type* as the newest used; a store that refuses the write leaves the list as it was. */
export const noteRecentType = (type: string, store: Store | null = browserStore()): void => {
  const next = [type, ...recentTypes(store).filter((one) => one !== type)].slice(0, RECENT_TYPES_SHOWN)
  try {
    store?.setItem(RECENT_TYPES_KEY, JSON.stringify(next))
  } catch {
    // Storage blocked or full: the list is a convenience, so it is simply not remembered.
  }
}
