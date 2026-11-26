import { describe, expect, it } from 'vitest'
import { fieldChange, shownRuns, wordRuns, type WordRun } from './fieldChange'

const text = (runs: readonly WordRun[], kind: WordRun['kind']): string[] =>
  runs.filter((run) => run.kind === kind).map((run) => run.words.join('').trim())

describe('wordRuns', () => {
  it('marks only the words that changed, and gives each side back when its runs are joined', () => {
    const before = 'Reads the drawing and answers its layout.'
    const after = 'Reads the stored drawing and answers its layout quickly.'
    const runs = wordRuns(before, after)
    expect(text(runs, 'added')).toEqual(['stored', 'layout quickly.'])
    expect(text(runs, 'removed')).toEqual(['layout.'])
    const side = (left: WordRun['kind']) => runs.filter((run) => run.kind !== left).flatMap((run) => run.words).join('')
    expect(side('removed')).toBe(after)
    expect(side('added').trim()).toBe(before)
  })

  it('puts a replacement as the removal followed by the insertion', () => {
    expect(wordRuns('one two three', 'one four three').map((run) => run.kind)).toEqual(['same', 'removed', 'added', 'same'])
  })

  it('compares words without the whitespace after them', () => {
    expect(wordRuns('a  b\nc', 'a b c').every((run) => run.kind === 'same')).toBe(true)
  })

  it('reads an empty side as all removed or all added', () => {
    expect(wordRuns('', 'two words').map((run) => run.kind)).toEqual(['added'])
    expect(wordRuns('two words', '').map((run) => run.kind)).toEqual(['removed'])
  })
})

describe('shownRuns', () => {
  const words = (count: number) => Array.from({ length: count }, (_, index) => `w${index} `)

  it('folds a long unchanged run between two changes, keeping four words beside each', () => {
    const shown = shownRuns([
      { kind: 'added', words: ['x '] }, { kind: 'same', words: words(30) }, { kind: 'removed', words: ['y '] },
    ])
    expect(shown.map((run) => [run.kind, run.words.length])).toEqual([
      ['added', 1], ['same', 4], ['folded', 22], ['same', 4], ['removed', 1],
    ])
  })

  it('keeps no words before a change at the start or after one at the end', () => {
    const shown = shownRuns([{ kind: 'same', words: words(20) }, { kind: 'added', words: ['x '] }])
    expect(shown.map((run) => [run.kind, run.words.length])).toEqual([['folded', 16], ['same', 4], ['added', 1]])
  })

  it('shows an unchanged run whole where fewer than six words would fold', () => {
    const between: WordRun[] = [
      { kind: 'added', words: ['x '] }, { kind: 'same', words: words(13) }, { kind: 'added', words: ['y '] },
    ]
    expect(shownRuns(between)).toEqual(between)
    expect(shownRuns([...between.slice(0, 1), { kind: 'same', words: words(14) }, ...between.slice(2)])
      .map((run) => run.kind)).toEqual(['added', 'same', 'folded', 'same', 'added'])
  })

  it('shows a short unchanged run whole', () => {
    const runs: WordRun[] = [{ kind: 'same', words: words(8) }, { kind: 'added', words: ['x '] }]
    expect(shownRuns(runs)).toEqual(runs)
  })
})

describe('fieldChange', () => {
  it('compares prose word by word', () => {
    expect(fieldChange('the old summary', 'the new summary').kind).toBe('text')
    expect(fieldChange('Draft', 'a longer summary now').kind).toBe('text')
  })

  it('replaces a short scalar whole: an enum, an id, a number, an absent side', () => {
    expect(fieldChange('draft', 'candidate')).toEqual({ kind: 'replaced', before: 'draft', after: 'candidate' })
    expect(fieldChange('SRV@1.a', 'SRV@2.b').kind).toBe('replaced')
    expect(fieldChange(3, 4)).toEqual({ kind: 'replaced', before: '3', after: '4' })
    expect(fieldChange(undefined, 'a new summary here')).toEqual({ kind: 'replaced', before: null, after: 'a new summary here' })
    expect(fieldChange('', null)).toEqual({ kind: 'replaced', before: null, after: null })
  })

  it('names each key of a keyed field that changed, and compares that key alone', () => {
    const change = fieldChange(
      { owner: 'Platform team', note: 'kept as it is', tier: 'gold' },
      { owner: 'Platform engineering team', note: 'kept as it is', sla: '99.9' },
    )
    const entries = change.kind === 'keyed' ? change.entries : []
    expect(entries.map((entry) => entry.key)).toEqual(['owner', 'sla', 'tier'])
    const owner = fieldChange(entries[0].before, entries[0].after)
    expect(owner.kind === 'text' ? text(owner.runs, 'added') : []).toEqual(['engineering'])
  })
})
