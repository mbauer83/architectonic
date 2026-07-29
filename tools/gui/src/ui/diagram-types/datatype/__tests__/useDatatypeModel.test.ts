import { describe, expect, it } from 'vitest'
import { useDatatypeModel } from '../useDatatypeModel'
import type { Classifier } from '../useDatatypeModel'

/** Minimal in-memory store standing in for the diagram-entities prop + patch emit. */
function harness(initial: Record<string, unknown> = {}) {
  let state: Record<string, unknown> = { ...initial }
  const model = useDatatypeModel(
    () => state,
    (patch) => { state = { ...state, ...patch } },
  )
  return { model, get: () => state }
}

const clf = (over: Partial<Classifier> = {}): Classifier => ({
  id: 'CLF@1.a.user', classifier_kind: 'class', label: 'User', ...over,
})

describe('useDatatypeModel — attribute ids', () => {
  it('mints a stable id when adding an attribute', () => {
    const { model, get } = harness({ classifier: [clf({ attributes: [] })] })
    model.addAttribute('CLF@1.a.user')
    const attrs = (get().classifier as Classifier[])[0].attributes!
    expect(attrs).toHaveLength(1)
    expect(attrs[0].id).toBeTruthy()
  })

  it('keeps identity / unique_keys intact when an attribute is renamed (id references)', () => {
    const { model, get } = harness({
      classifier: [clf({
        attributes: [{ id: 'a1', name: 'email' }],
        identity: ['a1'],
        unique_keys: [{ name: 'email', attribute_ids: ['a1'] }],
      })],
    })
    model.updateAttribute('CLF@1.a.user', 0, { name: 'emailAddress' })
    const c = (get().classifier as Classifier[])[0]
    expect(c.attributes![0].name).toBe('emailAddress')
    expect(c.identity).toEqual(['a1'])
    expect(c.unique_keys).toEqual([{ name: 'email', attribute_ids: ['a1'] }])
  })
})

describe('useDatatypeModel — generalization sets', () => {
  it('adds a set defaulting to complete + disjoint', () => {
    const { model, get } = harness({ classifier: [clf()] })
    model.addGeneralizationSet('GSET@1.x.m', 'method')
    const sets = get().generalization_set as Array<Record<string, unknown>>
    expect(sets).toEqual([{ id: 'GSET@1.x.m', label: 'method', is_covering: true, is_disjoint: true }])
  })

  it('clears the set reference on connections when the set is removed', () => {
    const { model, get } = harness({
      classifier: [clf()],
      generalization_set: [{ id: 'GSET@1.x.m', label: 'method' }],
      _connections: [{
        id: 'e1', conn_type: 'dt-generalization', source: 'a', target: 'b',
        generalization_set: 'GSET@1.x.m',
      }],
    })
    model.removeGeneralizationSet('GSET@1.x.m')
    expect(get().generalization_set).toEqual([])
    const conn = (get()._connections as Array<Record<string, unknown>>)[0]
    expect(conn.generalization_set).toBeUndefined()
  })
})
