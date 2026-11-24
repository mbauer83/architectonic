// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { useEditPanel } from '../useEditPanel'

beforeEach(() => { localStorage.clear() })

describe('the edit panel (Q22)', () => {
  it('opens on a diagram that fits, and starts closed on one too large to see whole', () => {
    const small = useEditPanel(() => false)
    small.opened()
    expect(small.open.value).toBe(true)
    const large = useEditPanel(() => true)
    large.opened()
    expect(large.open.value).toBe(false)
  })

  it('remembers the reader\'s choice per browser, over the default for the size', () => {
    const first = useEditPanel(() => false)
    first.opened()
    first.toggle()
    expect(first.open.value).toBe(false)
    const next = useEditPanel(() => false)
    next.opened()
    expect(next.open.value).toBe(false)
    next.toggle()
    const large = useEditPanel(() => true)
    large.opened()
    expect(large.open.value).toBe(true)
  })
})
