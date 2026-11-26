// @vitest-environment jsdom
/**
 * A changed text field read word by word (D31): a rewritten summary showed the whole old text struck
 * through beside the whole new text, so a reviewer compared two paragraphs by eye to find what moved.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import FieldChangeView from '../FieldChangeView.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

const render = (before: unknown, after: unknown): HTMLElement => {
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(FieldChangeView, { before, after }) })
  app.mount(host)
  return host
}

/** What a reader sees of *elements*: their text, without what is said only to a screen reader. */
const seen = (elements: Iterable<Element>): string[] => [...elements].map((element) => {
  const copy = element.cloneNode(true) as Element
  copy.querySelectorAll('.sr').forEach((hidden) => hidden.remove())
  return (copy.textContent ?? '').trim()
})

/** Sixty words of a summary, with three of them changed in *after*. */
const SUMMARY = Array.from({ length: 60 }, (_, index) => `word${index}`)
const before = SUMMARY.join(' ')
const after = SUMMARY.map((word, index) => ({ 10: 'reads', 30: 'stores', 50: 'answers' })[index] ?? word).join(' ')

describe('FieldChangeView', () => {
  it('marks exactly the three words that changed in a sixty-word summary, and strikes nothing unchanged', async () => {
    const host = render(before, after)
    await nextTick()
    expect(seen(host.querySelectorAll('ins'))).toEqual(['reads', 'stores', 'answers'])
    expect(seen(host.querySelectorAll('del'))).toEqual(['word10', 'word30', 'word50'])
    expect([...host.querySelectorAll('.fc-same')].every((same) => !same.closest('del'))).toBe(true)
    // Words 11–29 and 31–49 are long enough to fold; the short runs at either end are shown whole.
    expect(host.querySelectorAll('.fc-fold')).toHaveLength(2)
  })

  it('opens a folded stretch of unchanged words on a press, plain and unstruck', async () => {
    const host = render(before, after)
    await nextTick()
    const fold = host.querySelector<HTMLButtonElement>('.fc-fold')!
    expect(fold.textContent).toContain('11 words unchanged')
    expect(host.textContent).not.toContain('word20')
    fold.click()
    await nextTick()
    expect(host.querySelectorAll('.fc-fold')).toHaveLength(1)
    expect(host.textContent).toContain('word14 word15 word16 word17 word18 word19 word20')
    expect(seen(host.querySelectorAll('del'))).toEqual(['word10', 'word30', 'word50'])
  })

  it('says a removal and an insertion in words, not by colour alone', async () => {
    const host = render('the old text', 'the new text')
    await nextTick()
    expect(host.querySelector('del')?.textContent).toBe('removed: old ')
    expect(host.querySelector('ins')?.textContent).toBe('added: new ')
  })

  it('replaces a short scalar whole', async () => {
    const host = render('draft', 'candidate')
    await nextTick()
    expect(seen(host.querySelectorAll('del'))).toEqual(['draft'])
    expect(seen(host.querySelectorAll('ins'))).toEqual(['candidate'])
  })

  it('names the key of a keyed field and compares that key\'s value alone', async () => {
    const host = render(
      { owner: 'Platform team', tier: 'gold' },
      { owner: 'Platform engineering team', tier: 'gold' },
    )
    await nextTick()
    expect(seen(host.querySelectorAll('.fc-key-name'))).toEqual(['owner:'])
    expect(seen(host.querySelectorAll('ins'))).toEqual(['engineering'])
    expect(host.querySelectorAll('del')).toHaveLength(0)
  })
})
