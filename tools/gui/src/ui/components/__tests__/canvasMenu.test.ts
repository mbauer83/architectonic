// @vitest-environment jsdom
/**
 * The menu every canvas popover draws (sketch 03·5): it opens on its first entry, the arrows walk and
 * wrap, Home and End go to the ends, Enter chooses, a disabled entry is reached but not chosen, Escape
 * asks to close; a hint describes an entry without becoming part of its name.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import type { App } from 'vue'
import CanvasMenu from '../CanvasMenu.vue'
import { type CanvasMenuItem, menuStep } from '../canvasMenu'
import { elementMenuItems } from '../canvasElementMenu'
import { CANDIDATE_WORDS, DIAGRAM_WORDS } from '../canvasWords'

const ITEMS: readonly CanvasMenuItem[] = [
  { id: 'rename', label: 'Rename', hint: 'also a double-click on it', shortcut: 'F2' },
  { id: 'open', label: 'Open', disabled: true },
  { id: 'delete', label: 'Delete from model…', danger: true, divider: true },
]

let app: App | null = null
afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

const mounted = async () => {
  const choose = vi.fn()
  const close = vi.fn()
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(CanvasMenu, { items: ITEMS, heading: 'Record', onChoose: choose, onClose: close }) })
  app.mount(host)
  await nextTick()
  await nextTick()
  const entries = [...host.querySelectorAll<HTMLElement>('[role="menuitem"]')]
  const press = (key: string) =>
    (document.activeElement ?? host).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
  return { host, entries, choose, close, press }
}

describe('where the keys move focus', () => {
  it('steps and wraps with the arrows, and goes to the ends with Home and End', () => {
    expect(menuStep('ArrowDown', 0, 3)).toBe(1)
    expect(menuStep('ArrowDown', 2, 3)).toBe(0)
    expect(menuStep('ArrowUp', 0, 3)).toBe(2)
    expect(menuStep('ArrowDown', -1, 3)).toBe(0)
    expect(menuStep('ArrowUp', -1, 3)).toBe(2)
    expect(menuStep('Home', 2, 3)).toBe(0)
    expect(menuStep('End', 0, 3)).toBe(2)
    expect(menuStep('a', 0, 3)).toBeNull()
    expect(menuStep('ArrowDown', -1, 0)).toBeNull()
  })
})

describe('a canvas menu', () => {
  it('opens on its first entry, as a menu of menu items', async () => {
    const { host, entries } = await mounted()
    expect(host.querySelector('[role="menu"]')?.getAttribute('aria-label')).toBe('Record')
    expect(entries).toHaveLength(3)
    expect(document.activeElement).toBe(entries[0])
  })

  it('walks with the arrows, Home and End, wrapping at the ends', async () => {
    const { entries, press } = await mounted()
    press('ArrowDown')
    expect(document.activeElement).toBe(entries[1])
    press('End')
    expect(document.activeElement).toBe(entries[2])
    press('ArrowDown')
    expect(document.activeElement).toBe(entries[0])
    press('ArrowUp')
    expect(document.activeElement).toBe(entries[2])
    press('Home')
    expect(document.activeElement).toBe(entries[0])
  })

  it('chooses an entry, never a disabled one, and asks to close on Escape', async () => {
    const { entries, choose, close, press } = await mounted()
    entries[0]?.click()
    expect(choose).toHaveBeenCalledWith('rename')
    entries[1]?.click()
    expect(choose).toHaveBeenCalledTimes(1)
    expect(entries[1]?.getAttribute('aria-disabled')).toBe('true')
    press('Escape')
    expect(close).toHaveBeenCalled()
  })

  it('names an entry by its label and describes it by its hint, with the key at the right', async () => {
    const { entries, host } = await mounted()
    const [rename] = entries
    expect(document.getElementById(rename.getAttribute('aria-labelledby')!)?.textContent).toBe('Rename')
    expect(document.getElementById(rename.getAttribute('aria-describedby')!)?.textContent)
      .toBe('also a double-click on it')
    expect(rename.querySelector('.canvas-menu__key')?.textContent).toBe('F2')
    expect(host.querySelectorAll('[role="separator"]')).toHaveLength(1)
    expect(entries[2]?.classList.contains('canvas-menu__entry--danger')).toBe(true)
  })
})

describe("an element's menu", () => {
  it('lists what the editor can do, removing before the destructive entry at the bottom', () => {
    const ids = elementMenuItems(DIAGRAM_WORDS, false).map((one) => one.id)
    expect(ids).toEqual([
      'rename', 'details', 'connect', 'open', 'nest', 'stack:front', 'stack:forward', 'stack:backward', 'stack:back', 'remove', 'delete',
    ])
    const last = elementMenuItems(DIAGRAM_WORDS, false).at(-1)
    expect(last?.danger).toBe(true)
    expect(last?.hint).toBe(DIAGRAM_WORDS.deleteHint)
  })

  it('offers to take an element out of the diagram\'s own box it is in, naming the box', () => {
    const items = elementMenuItems(DIAGRAM_WORDS, false, 'Desk')
    expect(items.find((one) => one.id === 'unnest')?.label).toBe('Take out of Desk')
    expect(elementMenuItems(DIAGRAM_WORDS, false).some((one) => one.id === 'unnest')).toBe(false)
  })

  it('cannot open the page of an element drafted in this session', () => {
    expect(elementMenuItems(DIAGRAM_WORDS, true).find((one) => one.id === 'open')?.disabled).toBe(true)
  })

  it('says a candidate\'s words where the menu is a candidate\'s', () => {
    const items = elementMenuItems(CANDIDATE_WORDS, false)
    expect(items.find((one) => one.id === 'remove')?.label).toBe(CANDIDATE_WORDS.removeEntry)
    expect(items.find((one) => one.id === 'delete')?.label).toBe(CANDIDATE_WORDS.deleteEntry)
  })
})
