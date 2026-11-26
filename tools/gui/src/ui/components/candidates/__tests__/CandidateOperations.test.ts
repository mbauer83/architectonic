// @vitest-environment jsdom
/**
 * A candidate's operations against its base: an operation the base already holds — an applied candidate's —
 * reads as already there, never as its value struck and added again, and the page does not say the
 * candidate has no operations.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, h, ref, type App } from 'vue'
import { ALLOWED } from '../../../../domain/permissions'
import { permissionsKey } from '../../../keys'
import type { CandidateComparison, CandidateSummary } from '../../../../domain/schemas/candidates'
import type { Candidates } from '../../../composables/useCandidates'
import CandidateOperations from '../CandidateOperations.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

const SUMMARY: CandidateSummary = {
  id: 'CAND@1.a', name: 'Keywords', description: '', state: 'integrated', parent: null, scope: [], diagram: null,
  operations: 1,
}
const EDIT = { op: 'edit_entity', artifact_id: 'APP@1.idx', field: 'keywords', value: ['applied'],
  base: { value: ['search'] } }

const render = (comparison: Pick<CandidateComparison, 'standing' | 'diff'>) => {
  const candidates = {
    all: ref([SUMMARY]), selected: ref(SUMMARY.id), against: ref('model'),
    choices: ref([{ value: 'model', label: 'the current model' }]), error: ref(null),
    comparison: ref({
      candidate: SUMMARY.id, base: 'model', stack: [SUMMARY.id],
      view: { entities: [{ id: 'APP@1.idx', fields: { name: 'Indexer', keywords: ['applied'] } }], connections: [] },
      ...comparison,
    }),
    compareWith: () => undefined, describe: () => Promise.resolve(true),
  } as unknown as Candidates
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(CandidateOperations, { candidates, role: 'candidate', nameOf: (id: string) => id }) })
  app.provide(permissionsKey, computed(() => () => ALLOWED))
  app.mount(host)
  return host
}

describe('CandidateOperations', () => {
  it('reads an operation the base already holds as already there, struck and added nowhere', () => {
    const host = render({ diff: [], standing: [{ operation: EDIT, standing: 'already-there', reason: '' }] })
    const row = host.querySelector('[data-testid="already-there-row"]')
    expect(row?.textContent).toContain('Set keywords of Indexer to ["applied"]')
    expect(row?.textContent).toContain('already in the model')
    expect(host.querySelector('del')).toBeNull()
    expect(host.textContent).not.toContain('No operations against this base yet')
  })

  it('shows an edit the base does not hold yet as its change, and no already-there row', () => {
    const host = render({
      diff: [{ kind: 'entity', target: 'APP@1.idx', change: 'edited',
        fields: { keywords: { before: ['search'], after: ['applied'] } } }],
      standing: [{ operation: EDIT, standing: 'applies', reason: '' }],
    })
    expect(host.querySelector('[data-testid="already-there-row"]')).toBeNull()
    expect(host.querySelector('del')?.textContent).toContain('["search"]')
  })
})
