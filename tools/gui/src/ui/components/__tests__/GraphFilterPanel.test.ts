// @vitest-environment jsdom
//
// The filter's contract with a reader, through a real mount: what it *says* it is hiding matters as
// much as the hiding. A filter that quietly drops relations is the defect B30 fixed — a graph whose
// visible edge set depends on something the reader cannot see — shipped back as a feature, so the
// collapsed summary carrying the count and the reset is asserted, not assumed.
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import GraphFilterPanel from '../GraphFilterPanel.vue'
import type { FacetOptions } from '../../lib/graphFacets'

const level = (id: string, label: string, source: string) => ({
  id,
  label,
  source,
  required: true,
})

const ENTITY_FACETS: readonly FacetOptions[] = [
  { level: level('domain', 'Domain', 'hierarchy'), values: ['application', 'motivation'] },
  { level: level('entity_type', 'Entity type', 'type'), values: ['goal', 'outcome'] },
]
const RELATION_FACETS: readonly FacetOptions[] = [
  {
    level: level('connection_type', 'Relationship type', 'type'),
    values: ['archimate-realization'],
  },
]

let mounted: App | null = null
const events: unknown[][] = []

const render = (props: Record<string, unknown> = {}) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({
    render: () =>
      h(GraphFilterPanel, {
        entityFacets: ENTITY_FACETS,
        relationFacets: RELATION_FACETS,
        selection: {},
        excluded: 0,
        shown: 3,
        loaded: 3,
        onToggle: (...args: unknown[]) => events.push(['toggle', ...args]),
        onReset: () => events.push(['reset']),
        ...props,
      }),
  })
  app.mount(host)
  mounted = app
  return host
}

afterEach(() => {
  mounted?.unmount()
  mounted = null
  events.length = 0
  document.body.innerHTML = ''
})

const summaryText = (host: HTMLElement) => (host.querySelector('.disclosure')?.textContent ?? '').trim()
const valueButtons = (host: HTMLElement) =>
  [...host.querySelectorAll('.value')].map((b) => (b.textContent ?? '').trim())

describe('collapsed, it still says what it is doing', () => {
  it('says only "Filter" when nothing is excluded, and offers no reset', () => {
    const host = render()

    expect(summaryText(host)).toBe('▸ Filter')
    expect(host.querySelector('.reset')).toBeNull()
  })

  it('reports how much of the graph survives, since the consequence is not proportional to the cause', () => {
    // Excluding one relationship type takes with it everything it cut off from the anchor, which
    // was measured at a third of a graph. A reader who cannot see that has to infer it.
    const host = render({ selection: { domain: ['motivation'] }, excluded: 1, shown: 22, loaded: 33 })

    expect(summaryText(host)).toContain('22 of 33 shown')
  })

  it('says nothing about the count when the filter took nothing away', () => {
    const host = render({ selection: { domain: ['motivation'] }, excluded: 1, shown: 33, loaded: 33 })

    expect(summaryText(host)).not.toContain('of 33')
  })

  it('reports the excluded count and offers a clear on the same line', () => {
    const host = render({ selection: { domain: ['motivation'] }, excluded: 1 })

    expect(summaryText(host)).toContain('1 excluded')
    const clear = host.querySelector('.summary .reset')
    expect(clear).not.toBeNull()
    // Not "Reset": the viewport control on this surface is a Reset, and resets the framing.
    expect(clear?.textContent?.trim()).toBe('Clear')
  })

  it('emits its clear without the panel having to be opened', () => {
    const host = render({ selection: { domain: ['motivation'] }, excluded: 1 })

    host.querySelector<HTMLButtonElement>('.reset')?.click()

    expect(events).toEqual([['reset']])
  })
})

describe('what it offers', () => {
  it('renders nothing at all when the graph offers no facet', () => {
    const host = render({ entityFacets: [], relationFacets: [] })

    // Not an empty control: a filter with nothing to filter on is noise on the toolbar.
    expect(host.querySelector('.graph-filter')).toBeNull()
  })

  it('groups the levels by what they classify, under the label each declares', () => {
    const host = render()
    host.querySelector<HTMLButtonElement>('.disclosure')?.click()

    const headings = [...host.querySelectorAll('.heading')].map((h) => h.textContent?.trim())
    const levels = [...host.querySelectorAll('.level-label')].map((h) => h.textContent?.trim())

    expect(headings).toEqual(['Elements', 'Relationships'])
    // The labels are the meta-ontology's, rendered as given — this names none of them itself.
    expect(levels).toEqual(['Domain', 'Entity type', 'Relationship type'])
  })

  it('renders a value as words rather than as a slug', () => {
    const host = render()
    host.querySelector<HTMLButtonElement>('.disclosure')?.click()

    expect(valueButtons(host)).toContain('archimate realization')
  })

  it('emits the level id and the value, so the caller need not parse a label', () => {
    const host = render()
    host.querySelector<HTMLButtonElement>('.disclosure')?.click()
    const goal = [...host.querySelectorAll<HTMLButtonElement>('.value')].find(
      (b) => b.textContent?.trim() === 'goal',
    )

    goal?.click()

    expect(events).toEqual([['toggle', 'entity_type', 'goal']])
  })
})

describe('an excluded value looks excluded', () => {
  it('marks it struck through and un-pressed, so the state is not colour alone', () => {
    const host = render({ selection: { entity_type: ['goal'] }, excluded: 1 })
    host.querySelector<HTMLButtonElement>('.disclosure')?.click()
    const buttons = [...host.querySelectorAll<HTMLButtonElement>('.value')]
    const goal = buttons.find((b) => b.textContent?.trim() === 'goal')
    const outcome = buttons.find((b) => b.textContent?.trim() === 'outcome')

    expect(goal?.classList.contains('excluded')).toBe(true)
    expect(goal?.getAttribute('aria-pressed')).toBe('false')
    expect(outcome?.classList.contains('excluded')).toBe(false)
    expect(outcome?.getAttribute('aria-pressed')).toBe('true')
  })
})

describe('the disclosure is a disclosure', () => {
  it('starts collapsed and reports its own state', async () => {
    const host = render()
    const disclosure = host.querySelector<HTMLButtonElement>('.disclosure')

    expect(disclosure?.getAttribute('aria-expanded')).toBe('false')
    expect(disclosure?.getAttribute('aria-controls')).toBe('graph-filter-body')

    disclosure?.click()
    await nextTick()

    expect(disclosure?.getAttribute('aria-expanded')).toBe('true')
  })

  it('hides the body until it is opened, without unmounting it', async () => {
    // `v-show`, so the values stay in the accessibility tree's reach and the open is instant.
    const host = render()
    const body = host.querySelector<HTMLElement>('#graph-filter-body')

    expect(body?.style.display).toBe('none')

    host.querySelector<HTMLButtonElement>('.disclosure')?.click()
    await nextTick()

    expect(body?.style.display).not.toBe('none')
  })
})
