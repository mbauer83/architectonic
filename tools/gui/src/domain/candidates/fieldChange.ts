/**
 * A field's change, as a reader reviews it: what a candidate leaves of the base's value and what it puts
 * in. Text is compared word by word, so a rewritten summary shows the words that moved and not two
 * paragraphs side by side; a short scalar — an enum, an id, a number — is shown replaced whole; a keyed
 * field (`properties`) names each key that changed and compares that key's value alone.
 *
 * Pure and independent of how it is drawn: `FieldChangeView` renders it, wherever a candidate's field
 * changes are read.
 */

/** A run of words the two values share, or that only the base (`removed`) or the candidate (`added`) has. */
export interface WordRun {
  readonly kind: 'same' | 'removed' | 'added'
  /** Each word with the whitespace that followed it, so joining them gives the text back. */
  readonly words: readonly string[]
}

/** A run as it is shown: an unchanged run too long to read in full is folded, keeping a few words each side. */
export type ShownRun =
  | WordRun
  | { readonly kind: 'folded'; readonly words: readonly string[] }

export type FieldChange =
  | { readonly kind: 'text'; readonly runs: readonly WordRun[] }
  | { readonly kind: 'replaced'; readonly before: string | null; readonly after: string | null }
  | { readonly kind: 'keyed'; readonly entries: readonly KeyChange[] }

/** One key of a keyed field that changed: its value in the base and in the candidate. */
export interface KeyChange {
  readonly key: string
  readonly before: unknown
  readonly after: unknown
}

/** How many words of an unchanged run stay in view beside a change when the rest of it is folded. */
export const KEPT_BESIDE_A_CHANGE = 4
/** An unchanged run this long or shorter is always shown whole. */
const SHOWN_WHOLE = 2 * KEPT_BESIDE_A_CHANGE + 3
/**
 * Above this many word pairs the comparison is not made and the value is shown replaced whole. The table is
 * quadratic; this is roughly two texts of 2,000 words each, far beyond a field anyone reviews word by word.
 */
const LARGEST_COMPARISON = 4_000_000

type Mapping = Readonly<Record<string, unknown>>

const isMapping = (value: unknown): value is Mapping =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

/** A value as text, or null where there is none. */
export const valueText = (value: unknown): string | null =>
  value === null || value === undefined || value === ''
    ? null
    : typeof value === 'string' ? value : JSON.stringify(value)

/** Whether *text* is prose rather than a scalar: more than one word. */
const isProse = (text: string): boolean => /\S\s+\S/.test(text.trim())

/** The words of *text*, each with the whitespace after it; leading whitespace is not a word. */
export const wordsOf = (text: string): string[] => text.trimStart().match(/\S+\s*/g) ?? []

const bare = (word: string): string => word.trimEnd()

/** The longest-common-subsequence table over two word lists, read from the end: `table[i][j]` for the tails. */
const commonTable = (left: readonly string[], right: readonly string[]): Uint32Array[] => {
  const table = Array.from({ length: left.length + 1 }, () => new Uint32Array(right.length + 1))
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      table[i][j] = bare(left[i]) === bare(right[j])
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  return table
}

/** Appends *word* to the last run when it is of *kind*, else opens a run. */
const pushed = (runs: WordRun[], kind: WordRun['kind'], word: string): WordRun[] => {
  const last = runs.at(-1)
  if (last?.kind === kind) runs[runs.length - 1] = { kind, words: [...last.words, word] }
  else runs.push({ kind, words: [word] })
  return runs
}

/**
 * The word runs that turn *before* into *after*: the words both share in order (the longest common
 * subsequence), and between them what was taken out and what was put in, the removal first. Words are
 * compared without the whitespace after them, and the candidate's spacing is the one shown.
 */
export const wordRuns = (before: string, after: string): WordRun[] => {
  const left = wordsOf(before)
  const right = wordsOf(after)
  const table = commonTable(left, right)
  const runs: WordRun[] = []
  let i = 0
  let j = 0
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && bare(left[i]) === bare(right[j])) {
      pushed(runs, 'same', right[j])
      i += 1
      j += 1
    } else if (j >= right.length || (i < left.length && table[i + 1][j] >= table[i][j + 1])) {
      pushed(runs, 'removed', left[i])
      i += 1
    } else {
      pushed(runs, 'added', right[j])
      j += 1
    }
  }
  return runs
}

/** Splits an unchanged run too long to read whole: a few words kept beside each change, the rest folded. */
const folding = (run: WordRun, first: boolean, last: boolean): ShownRun[] => {
  const head = first ? 0 : KEPT_BESIDE_A_CHANGE
  const tail = last ? 0 : KEPT_BESIDE_A_CHANGE
  if (run.kind !== 'same' || run.words.length <= SHOWN_WHOLE || run.words.length - head - tail < 2) return [run]
  const folded: ShownRun = { kind: 'folded', words: run.words.slice(head, run.words.length - tail) }
  return [
    ...(head ? [{ kind: 'same' as const, words: run.words.slice(0, head) }] : []),
    folded,
    ...(tail ? [{ kind: 'same' as const, words: run.words.slice(run.words.length - tail) }] : []),
  ]
}

/** The runs as they are shown: every long unchanged run folded, keeping the words beside each change. */
export const shownRuns = (runs: readonly WordRun[]): ShownRun[] =>
  runs.flatMap((run, index) => folding(run, index === 0, index === runs.length - 1))

/** What changed between *before* and *after*, read as a reviewer reads it (see the module's note). */
export const fieldChange = (before: unknown, after: unknown): FieldChange => {
  if (isMapping(before) && isMapping(after)) {
    const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()
    return {
      kind: 'keyed',
      entries: keys
        .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
        .map((key) => ({ key, before: before[key], after: after[key] })),
    }
  }
  if (typeof before === 'string' && typeof after === 'string' && (isProse(before) || isProse(after))
    && wordsOf(before).length * wordsOf(after).length <= LARGEST_COMPARISON) {
    return { kind: 'text', runs: wordRuns(before, after) }
  }
  return { kind: 'replaced', before: valueText(before), after: valueText(after) }
}
