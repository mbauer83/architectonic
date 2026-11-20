import type {
  Area, ClassificationLevel, Note, Scratchpad,
} from '../../domain/schemas/scratchpads'
import { withNote, without, withoutType } from './scratchpadEdits'

/**
 * A note's refinement, read through the levels its scratchpad's meta-ontology declares.
 *
 * The server sends the ladder with the scratchpad: which levels there are, in what order, what
 * each offers and which are required. Everything here walks that list. No level is named in this
 * file — a meta-ontology declaring two levels, or five, or calling them something else, gets one
 * control per level it declared.
 *
 * What a note stores is keyed by where a level's values *come from*, never by what the level is
 * called: the wire keeps the three keys it has always had under any declaration.
 */

type LevelKey = 'domain' | 'element-type' | 'specialization'

const KEY_OF: Readonly<Record<ClassificationLevel['source'], LevelKey>> = {
  hierarchy: 'domain',
  type: 'element-type',
  specializations: 'specialization',
}

/** The value the note holds at *level*, or `undefined`. */
export function valueAt(note: Note, level: ClassificationLevel): string | undefined {
  return note[KEY_OF[level.source]]
}

/** Whether the note has answered *level*, by choosing or by implication: a type implies its
 * hierarchy, so choosing one reaches every level above it that takes its values from there. */
function isReached(note: Note, level: ClassificationLevel): boolean {
  return valueAt(note, level) !== undefined
    || (level.source === 'hierarchy' && note['element-type'] !== undefined)
}

/** The level whose attribute schema applies to the note — the deepest reached one the
 * meta-ontology says carries attributes — or `null` while the note is below every such level. */
export function attributeLevel(
  note: Note, levels: readonly ClassificationLevel[],
): ClassificationLevel | null {
  return levels.filter((level) => level['carries-attributes'] && isReached(note, level)).at(-1) ?? null
}

/** What an area permits at *level*, or `null` where it says nothing about that level. */
function permittedAt(area: Area | null, level: ClassificationLevel): readonly string[] | null {
  const permitted = level.source === 'hierarchy'
    ? area?.['permitted-domains']
    : level.source === 'type' ? area?.['permitted-element-types'] : undefined
  return permitted?.length ? permitted : null
}

export interface OfferedOption {
  readonly value: string
  /** Outside what the note's area permits: still offered, and marked rather than hidden, because
   * an area narrows as a warning and the choice is one the ontology declares. */
  readonly outsideArea: boolean
}

/**
 * What *level* offers this note: what the level above allows, the area's permitted values first.
 *
 * "The level above" is the nearest declared level the note has a value at. An option names the
 * value it belongs to there; one that names none is offered under any.
 */
export function optionsAt(
  note: Note, level: ClassificationLevel, levels: readonly ClassificationLevel[], area: Area | null,
): OfferedOption[] {
  const position = levels.findIndex((candidate) => candidate.id === level.id)
  const above = position > 0 ? valueAt(note, levels[position - 1]) : undefined
  const permitted = permittedAt(area, level)
  const offered = (level.options ?? [])
    .filter((option) => !option.within || !above || option.within === above)
    .map((option) => ({
      value: option.value,
      outsideArea: permitted !== null && !permitted.includes(option.value),
    }))
  return [
    ...offered.filter((option) => !option.outsideArea),
    ...offered.filter((option) => option.outsideArea),
  ]
}

const findNote = (scratchpad: Scratchpad, noteId: string): Note | undefined =>
  (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)

/** The keys of every level declared after *levelId*. */
function finerKeys(levels: readonly ClassificationLevel[], levelId: string): LevelKey[] {
  const position = levels.findIndex((candidate) => candidate.id === levelId)
  return levels.slice(position + 1).map((level) => KEY_OF[level.source])
}

/** What choosing *value* at the level in *position* implies at every level above it.
 *
 * An option names the value it belongs to one level up, and that one names its own, so a choice
 * made at a fine level answers the coarser ones — which the server derives on the next read
 * anyway. Setting them here keeps the card from lagging a save behind. */
function implied(
  levels: readonly ClassificationLevel[], position: number, value: string,
): Partial<Record<LevelKey, string>> {
  const within = levels[position]?.options?.find((option) => option.value === value)?.within
  const above = levels[position - 1]
  if (!above || !within) return {}
  return { ...implied(levels, position - 1, within), [KEY_OF[above.source]]: within }
}

/**
 * Narrow a note to *value* at one declared level, re-opening every level declared after it.
 *
 * Mirrors the aggregate's one refinement step. Refused server-side on a note tied to the model,
 * so nothing happens here either.
 */
export function withLevelValue(
  scratchpad: Scratchpad, noteId: string, levelId: string, value: string,
): Scratchpad {
  const levels = scratchpad['classification-levels'] ?? []
  const position = levels.findIndex((candidate) => candidate.id === levelId)
  const note = findNote(scratchpad, noteId)
  if (position < 0 || !note || note['model-ref']) return scratchpad
  return withNote(scratchpad, {
    ...without(note, ...finerKeys(levels, levelId), 'document-type'),
    destination: 'element',
    ...implied(levels, position, value),
    [KEY_OF[levels[position].source]]: value,
  })
}

/**
 * Re-open *levelId* and every level declared after it. A note left with nothing decided returns to
 * undecided, exactly as untyping it does.
 */
export function withoutLevelValue(
  scratchpad: Scratchpad, noteId: string, levelId: string,
): Scratchpad {
  const levels = scratchpad['classification-levels'] ?? []
  const level = levels.find((candidate) => candidate.id === levelId)
  const note = findNote(scratchpad, noteId)
  if (!level || !note || note['model-ref']) return scratchpad
  const reopened = without(note, KEY_OF[level.source], ...finerKeys(levels, levelId))
  const stillDecided = levels.some((candidate) => valueAt(reopened, candidate) !== undefined)
  return stillDecided ? withNote(scratchpad, reopened) : withoutType(scratchpad, noteId)
}
