/**
 * The editing preferences are per browser and fail soft: defaults when nothing is remembered, the
 * choice read back after it is made, a stale or foreign value read as never made, and a refused
 * storage holding the choice for this page only. The keyboard layout is detected where the browser
 * can tell, and QWERTY is assumed where it cannot.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PREFERENCE_KEYS, editingPreferences } from '../useEditingPreferences'
import { detectKeyScheme, viewportKeyOf, zoomInKeyName } from '../../lib/keyboardScheme'

const memoryStorage = () => {
  const items = new Map<string, string>()
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => { items.set(key, value) },
    removeItem: (key: string) => { items.delete(key) },
    items,
  }
}
const refusingStorage = {
  getItem: () => { throw new Error('SecurityError') },
  setItem: () => { throw new Error('SecurityError') },
}
const qwerty = () => Promise.resolve({ scheme: 'qwerty' as const, how: 'test' })

describe('the editing preferences', () => {
  let storage: ReturnType<typeof memoryStorage>
  beforeEach(() => {
    storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('start from the defaults: touching, snapping, detected keys, the list only for model changes', () => {
    const prefs = editingPreferences(qwerty)
    expect(prefs.rectangle.value.value).toBe('touches')
    expect(prefs.snapping.value.value).toBe('snap')
    expect(prefs.keys.value.value).toBe('detect')
    expect(prefs.saveList.value.value).toBe('model')
  })

  it('remember a choice in this browser and read it back', () => {
    editingPreferences(qwerty).snapping.set('hints')
    editingPreferences(qwerty).saveList.set('always')
    expect(storage.items.get(PREFERENCE_KEYS.snapping)).toBe('hints')
    const again = editingPreferences(qwerty)
    expect([again.snapping.value.value, again.saveList.value.value]).toEqual(['hints', 'always'])
  })

  it('read a stored value that is not one of the choices as never made', () => {
    storage.items.set(PREFERENCE_KEYS.saveList, 'never')
    storage.items.set(PREFERENCE_KEYS.rectangle, 'crosses')
    const prefs = editingPreferences(qwerty)
    expect([prefs.saveList.value.value, prefs.rectangle.value.value]).toEqual(['model', 'touches'])
  })

  it('switch the rectangle rule with R and remember it', () => {
    const prefs = editingPreferences(qwerty)
    expect(prefs.switchRectangle()).toBe('encloses')
    expect(storage.items.get(PREFERENCE_KEYS.rectangle)).toBe('encloses')
    expect(prefs.switchRectangle()).toBe('touches')
  })

  it('hold a choice for this page when storage is refused', () => {
    vi.stubGlobal('localStorage', refusingStorage)
    const prefs = editingPreferences(qwerty)
    expect(prefs.rectangle.value.value).toBe('touches')
    prefs.rectangle.set('encloses')
    expect(prefs.rectangle.value.value).toBe('encloses')
  })

  it('name the keys for the chosen layout, else the detected one', async () => {
    const prefs = editingPreferences(() => Promise.resolve({ scheme: 'qwertz', how: 'test' }))
    expect(prefs.scheme.value).toBe('qwerty')
    await Promise.resolve()
    expect(prefs.scheme.value).toBe('qwertz')
    prefs.keys.set('qwerty')
    expect(prefs.scheme.value).toBe('qwerty')
  })
})

describe('the keyboard layout', () => {
  it('is QWERTZ where the key right of T types z', async () => {
    const keyboard = { getLayoutMap: () => Promise.resolve(new Map([['KeyY', 'z'], ['KeyZ', 'y']])) }
    expect((await detectKeyScheme({ keyboard })).scheme).toBe('qwertz')
  })

  it('is assumed QWERTY where the browser cannot tell, or refuses', async () => {
    expect((await detectKeyScheme({})).scheme).toBe('qwerty')
    const refusing = { keyboard: { getLayoutMap: () => Promise.reject(new Error('NotAllowed')) } }
    expect(await detectKeyScheme(refusing)).toMatchObject({ scheme: 'qwerty' })
  })
})

describe('the window keys', () => {
  const key = (k: string, more: Partial<KeyboardEvent> = {}) =>
    ({ key: k, ctrlKey: false, metaKey: false, altKey: false, ...more })

  it('fit with 0, zoom in with +, zoom out with − on either layout', () => {
    for (const scheme of ['qwerty', 'qwertz'] as const) {
      expect([viewportKeyOf(key('0'), scheme), viewportKeyOf(key('+'), scheme), viewportKeyOf(key('-'), scheme)])
        .toEqual(['fit', 'in', 'out'])
    }
  })

  it('bind = to zoom in on QWERTY only, and nothing under Ctrl', () => {
    expect(viewportKeyOf(key('='), 'qwerty')).toBe('in')
    expect(viewportKeyOf(key('='), 'qwertz')).toBeNull()
    expect(viewportKeyOf(key('0', { ctrlKey: true }), 'qwerty')).toBeNull()
    expect([zoomInKeyName('qwerty'), zoomInKeyName('qwertz')]).toEqual(['+ or =', '+'])
  })
})
