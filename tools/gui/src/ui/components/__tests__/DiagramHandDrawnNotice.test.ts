// @vitest-environment jsdom
//
// The edit-mode notice over a picture drawn by hand: one plain sentence first, then what only the hand-drawn
// picture has, collapsed, named as a reader sees the picture — never a PlantUML alias or arrow.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import DiagramHandDrawnNotice from '../DiagramHandDrawnNotice.vue'
import type { HandDrawn } from '../../../domain/schemas/diagrams'

/** A PlantUML alias as the renderer spells one, a further drawing's included: `ACT_Nn7Oo7__2`. */
const RAW_ALIAS = /[A-Z]{2,4}_\w+__\d/

const DRAWN: HandDrawn = {
  boxes: ['Team / Project A', 'Team / Project B'],
  elements: ['Architect'],
  relations: [
    { source: 'Architect', target: 'Engagement Repository', type: 'assignment' },
    { source: 'AI Agent', target: 'Engagement Repository' },
  ],
  directions: ['left to right'],
}

let app: App | null = null
let host: HTMLDivElement

const mounted = async (handDrawn?: HandDrawn): Promise<HTMLElement> => {
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(DiagramHandDrawnNotice, { handDrawn }) })
  app.mount(host)
  await nextTick()
  return host.querySelector<HTMLElement>('[data-testid="edit-body-by-hand"]')!
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('the notice over a picture drawn by hand', () => {
  it('says in one plain sentence what a save keeps and where to change what the picture draws', async () => {
    const notice = await mounted(DRAWN)
    expect(notice.querySelector('p')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      "This diagram's picture is drawn by hand. Arranging it is saved; adding or removing what it draws is not. "
      + 'To change what it draws, leave editing and choose Lay out automatically…, which replaces the hand-drawn '
      + 'picture with a generated one.',
    )
  })

  it('lists what only the hand-drawn picture has, collapsed until asked for', async () => {
    const notice = await mounted(DRAWN)
    const details = notice.querySelector<HTMLDetailsElement>('[data-testid="hand-drawn-details"]')!
    expect(details.open).toBe(false)
    expect(details.querySelector('summary')?.textContent).toBe('What only the hand-drawn picture has')
    expect([...details.querySelectorAll('li')].map((li) => li.textContent?.trim())).toEqual([
      'Box "Team / Project A"',
      'Box "Team / Project B"',
      'Element "Architect"',
      'Architect → Engagement Repository (assignment)',
      'AI Agent → Engagement Repository',
      'Laid out left to right',
    ])
  })

  it('shows no alias and no arrow anywhere in the notice', async () => {
    const notice = await mounted(DRAWN)
    expect(notice.textContent).not.toMatch(RAW_ALIAS)
    expect(notice.textContent).not.toMatch(/-->|\.\.>|-down-/)
  })

  it('has no details to open where the read names nothing', async () => {
    const notice = await mounted(undefined)
    expect(notice.querySelector('details')).toBeNull()
  })
})
