// @vitest-environment jsdom
//
// What the Reading panel shows and what it asks for. The reading itself is computed elsewhere and
// handed in; this holds the template to the decisions of sketch 05: controls named Incoming and
// Outgoing with four steps each, a latching flow toggle that is unavailable under reduced motion, and
// three honestly split lists whose rows outline their end on the diagram.

import { describe, expect, it } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import DiagramReaderPanel from '../DiagramReaderPanel.vue'
import type { Reach } from '../../../domain/diagramReading'

const props = (over: Record<string, unknown> = {}) => ({
  title: 'Enterprise Repository',
  reach: { incoming: 1, outgoing: 1 } as Reach,
  flowOn: false,
  reducedMotion: false,
  drawn: {
    incoming: [{ id: 'A', name: 'Promote Artifacts', type: 'process', domain: 'business' }],
    outgoing: [{ id: 'B', name: 'Engagement Repository', type: 'business-object', domain: 'business' }],
  },
  notDrawn: [
    { id: 'r1', here: 'S', other: 'X', otherName: 'Entity', otherDrawn: false, type: 'archimate-aggregation', way: 'outgoing' },
    { id: 'r2', here: 'S', other: 'Y', otherName: 'Proposed Change', otherDrawn: true, type: 'archimate-association',
      way: 'undirected' },
  ],
  derived: {
    certain: [{ entityId: 'C', name: 'Architect', type: 'archimate-association', way: 'undirected', hops: 2 }],
    potential: [{ entityId: 'D', name: 'Diagram', type: 'archimate-serving', way: 'incoming', hops: 3 }],
    loading: false, failed: false,
  },
  ...over,
})

const mount = (over: Record<string, unknown> = {}) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const events: [string, unknown][] = []
  const on = (name: string) => (value?: unknown) => { events.push([name, value]) }
  createApp({
    render: () => h(DiagramReaderPanel, {
      ...props(over),
      'onUpdate:reach': on('reach'), onToggleFlow: on('flow'), onFrame: on('frame'), onCopyLink: on('copy'),
      onClear: on('clear'), onSelect: on('select'), onHover: on('hover'),
    } as never),
  }).mount(host)
  const button = (selector: string) => host.querySelector<HTMLElement>(selector) as HTMLElement
  return { host, events, button }
}

describe('the Reading panel', () => {
  it('names the controls Incoming and Outgoing, with four steps each, and reports a new reach', () => {
    const { host, events, button } = mount()
    const groups = [...host.querySelectorAll('[role="group"]')].map((group) => group.getAttribute('aria-label'))
    expect(groups).toEqual(['Incoming reach', 'Outgoing reach'])
    expect([...host.querySelectorAll('[data-reach^="incoming"]')].map((one) => one.textContent?.trim()))
      .toEqual(['none', '1 step', '2 steps', 'all'])
    expect(button('[data-reach="incoming:1"]').getAttribute('aria-pressed')).toBe('true')
    button('[data-reach="outgoing:all"]').click()
    expect(events).toContainEqual(['reach', { incoming: 1, outgoing: 'all' }])
  })

  it('latches flow with a pressed state, and under reduced motion is unavailable and says why', () => {
    const on = mount({ flowOn: true })
    expect(on.button('[data-testid="reader-flow"]').getAttribute('aria-pressed')).toBe('true')
    expect(on.button('[data-testid="reader-flow"]').textContent).toContain('Animating')
    on.button('[data-testid="reader-flow"]').click()
    expect(on.events).toContainEqual(['flow', undefined])

    const reduced = mount({ flowOn: true, reducedMotion: true })
    const toggle = reduced.button('[data-testid="reader-flow"]')
    expect(toggle.getAttribute('aria-disabled')).toBe('true')
    expect(toggle.getAttribute('aria-pressed')).toBe('false')
    expect(reduced.host.textContent).toContain('reduced motion')
  })

  it('splits the lists honestly, and a row outlines its end on the diagram while hovered or focused', async () => {
    const { host, events, button } = mount()
    expect(button('[data-testid="reader-drawn"] summary').textContent).toContain('1 incoming · 1 outgoing')
    const notDrawn = host.querySelector('[data-testid="reader-not-drawn"]')?.textContent ?? ''
    expect(notDrawn).toContain('Outgoing')
    expect(notDrawn).toContain('Either way')
    expect(notDrawn).toContain('aggregation · not on this diagram')
    expect(host.querySelector('[data-testid="reader-derived"] summary')?.textContent).toContain('1 certain · 1 potential')
    expect(host.querySelector('[data-testid="reader-derived"]')?.textContent).toContain('association, either way · 2 hops')

    const reached = button('[data-reached="B"]')
    reached.dispatchEvent(new Event('mouseenter'))
    reached.click()
    const row = button('[data-testid="reader-not-drawn"] li.ent-item')
    row.dispatchEvent(new Event('focus'))
    row.dispatchEvent(new Event('blur'))
    await nextTick()
    expect(events).toEqual(expect.arrayContaining([['hover', 'B'], ['select', 'B'], ['hover', 'S'], ['hover', null]]))
  })

  it('says what it is still reading, what it could not, and when nothing is reached', () => {
    const { host } = mount({
      drawn: { incoming: [], outgoing: [] }, notDrawn: [],
      derived: { certain: [], potential: [], loading: true, failed: true },
    })
    expect(host.textContent).toContain('Nothing within this reach.')
    expect(host.textContent).toContain('Every relation the model has for the selection within this reach is drawn.')
    expect(host.querySelector('[data-testid="reader-derived"] summary')?.textContent).toContain('…')
    expect(host.textContent).toContain('could not be read')
  })

  it('asks to frame, copy the link and clear', () => {
    const { host, events, button } = mount()
    ;[...host.querySelectorAll<HTMLButtonElement>('.actions button')].forEach((one) => one.click())
    button('[aria-label="Clear the reading"]').click()
    expect(events.map(([name]) => name)).toEqual(['frame', 'copy', 'clear'])
  })
})
