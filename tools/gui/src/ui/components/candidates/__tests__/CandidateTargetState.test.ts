// @vitest-environment jsdom
/**
 * The target-state confirmation reads an edit as the apply confirmation does: against what the model holds where
 * it writes, from the dry run's standing. An edit stored against a revision says nothing of the value it was
 * written over, so without the standing it showed no change at all.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, h, nextTick, type App } from 'vue'
import { ALLOWED } from '../../../../domain/permissions'
import { permissionsKey } from '../../../keys'
import type { OperationStanding } from '../../../../domain/schemas/candidates'
import {
  type CandidateTargetStateAccess, type TargetPreview, useCandidateTargetState,
} from '../../../composables/useCandidateTargetState'
import CandidateTargetState from '../CandidateTargetState.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

const SERVICE = 'SRV@1712870400.Uv9Wx9'
const edit = {
  op: 'edit_entity', artifact_id: SERVICE, field: 'name', value: 'Promotion Review Service', base: { revision: 'r1' },
}
const activation = {
  op: 'edit_entity', artifact_id: 'APP@1.a', field: 'status', value: 'active', base: { value: 'draft' },
}

const render = async (preview: Omit<TargetPreview, 'candidate' | 'ids' | 'unheld' | 'refusal'>) => {
  const target = useCandidateTargetState({} as CandidateTargetStateAccess)
  target.preview.value = { candidate: 'CAND@1.a', ids: null, unheld: [], refusal: null, ...preview }
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(CandidateTargetState, { target, candidateId: 'CAND@1.a', name: 'Spec' }) })
  app.provide(permissionsKey, computed(() => () => ALLOWED))
  app.component('RouterLink', { render: () => null })
  app.mount(host)
  await nextTick()
  return [...host.querySelectorAll<HTMLElement>('[data-testid="field-change"]')]
}

describe('CandidateTargetState', () => {
  it('reads an edit stored against a revision against what the model holds where it writes', async () => {
    const standing: OperationStanding[] = [{ operation: edit, standing: 'applies', reason: '', holds: 'Review Service' }]
    const changes = await render({ write: 'move', operations: [edit], standing })
    expect(changes).toHaveLength(1)
    expect(changes[0].querySelector('ins')?.textContent).toContain('Promotion')
    expect(changes[0].querySelector('del')).toBeNull()
    expect(changes[0].textContent).toContain('Review Service')
  })

  it('finds each edit\'s standing by what it writes, whatever order the standings come in', async () => {
    const standing: OperationStanding[] = [
      { operation: activation, standing: 'applies', reason: '', holds: 'draft' },
      { operation: edit, standing: 'applies', reason: '', holds: 'Review Service' },
    ]
    const changes = await render({ write: 'move', operations: [edit, activation], standing })
    expect(changes).toHaveLength(2)
    expect(changes[0].textContent).toContain('Promotion Review Service')
    expect(changes[1].textContent).toContain('draft')
    expect(changes[1].textContent).toContain('active')
  })

  it('reads an edit with no standing against the value it says it was written over', async () => {
    const changes = await render({ write: 'withdraw', operations: [activation], standing: [] })
    expect(changes).toHaveLength(1)
    expect(changes[0].textContent).toContain('draft')
  })
})
