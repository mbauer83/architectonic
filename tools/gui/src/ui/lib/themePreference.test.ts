import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEME_STORAGE_KEY, applyThemeChoice, chooseTheme, readThemeChoice } from './themePreference'

const fakeRoot = () => {
  const attributes = new Map<string, string>()
  return {
    attributes,
    element: {
      setAttribute: (name: string, value: string) => { attributes.set(name, value) },
      removeAttribute: (name: string) => { attributes.delete(name) },
    } as unknown as HTMLElement,
  }
}

const memoryStorage = () => {
  const items = new Map<string, string>()
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => { items.set(key, value) },
    removeItem: (key: string) => { items.delete(key) },
    items,
  }
}

describe('the theme preference', () => {
  let storage: ReturnType<typeof memoryStorage>
  beforeEach(() => {
    storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('follows the system when nothing is remembered', () => {
    expect(readThemeChoice()).toBe('system')
  })

  it('remembers an explicit choice and puts it on the root', () => {
    const root = fakeRoot()
    chooseTheme('dark', root.element)
    expect(root.attributes.get('data-theme')).toBe('dark')
    expect(storage.items.get(THEME_STORAGE_KEY)).toBe('dark')
    expect(readThemeChoice()).toBe('dark')
  })

  it('returns to the system by forgetting the choice and removing the attribute', () => {
    const root = fakeRoot()
    chooseTheme('light', root.element)
    chooseTheme('system', root.element)
    expect(root.attributes.has('data-theme')).toBe(false)
    expect(storage.items.has(THEME_STORAGE_KEY)).toBe(false)
    expect(readThemeChoice()).toBe('system')
  })

  it('ignores a stored value that is not a theme', () => {
    storage.setItem(THEME_STORAGE_KEY, 'sepia')
    expect(readThemeChoice()).toBe('system')
  })

  it('still applies the choice when storage refuses', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('denied') },
      setItem: () => { throw new Error('denied') },
      removeItem: () => { throw new Error('denied') },
    })
    const root = fakeRoot()
    expect(readThemeChoice()).toBe('system')
    chooseTheme('dark', root.element)
    expect(root.attributes.get('data-theme')).toBe('dark')
    applyThemeChoice('system', root.element)
    expect(root.attributes.has('data-theme')).toBe(false)
  })
})
