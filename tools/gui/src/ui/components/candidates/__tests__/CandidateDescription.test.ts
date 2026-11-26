// @vitest-environment jsdom
/**
 * A candidate's core idea where it is read (D32): shown under its name, written in place where the reader may
 * change it, and only shown in a comparison, whose base is fixed.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, h, nextTick, type App } from 'vue'
import { ALLOWED } from '../../../../domain/permissions'
import { permissionsKey } from '../../../keys'
import type { CandidateSummary } from '../../../../domain/schemas/candidates'
import type { Candidates } from '../../../composables/useCandidates'
import CandidateDescription from '../CandidateDescription.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

const summary = (description: string): CandidateSummary => ({
  id: 'CAND@1.a', name: 'Rule set', description, state: 'draft', parent: null, scope: [], diagram: null, operations: 0,
})

const render = (description: string, editable: boolean) => {
  const described: [string, string][] = []
  const candidates: Pick<Candidates, 'describe'> = {
    describe: (id: string, text: string) => {
      described.push([id, text])
      return Promise.resolve(true)
    },
  }
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(CandidateDescription, { candidates, summary: summary(description), editable }) })
  app.provide(permissionsKey, computed(() => () => ALLOWED))
  app.mount(host)
  const find = <T extends HTMLElement>(id: string) => host.querySelector<T>(`[data-testid="${id}"]`)
  return { host, find, described }
}

describe('CandidateDescription', () => {
  it('shows the core idea under the name', () => {
    const { find } = render('Rules move out of the code.', false)
    expect(find('candidate-description')?.textContent).toContain('Rules move out of the code.')
    expect(find('describe-candidate')).toBeNull()
  })

  it('says nothing where there is no description and it may not be written', () => {
    const { find } = render('', false)
    expect(find('candidate-description')).toBeNull()
  })

  it('writes the core idea in place, trimmed, through the candidate\'s edit', async () => {
    const { find, described } = render('', true)
    expect(find('candidate-description')?.textContent).toContain('No description of its core idea yet.')
    find<HTMLButtonElement>('describe-candidate')!.click()
    await nextTick()
    const input = find<HTMLTextAreaElement>('candidate-description-input')!
    expect(input.maxLength).toBe(300)
    input.value = '  A queue absorbs the burst.  '
    input.dispatchEvent(new Event('input'))
    find<HTMLFormElement>('candidate-description-form')!.dispatchEvent(new Event('submit'))
    await nextTick()
    await nextTick()
    expect(described).toEqual([['CAND@1.a', 'A queue absorbs the burst.']])
    expect(find('candidate-description-form')).toBeNull()
  })
})
