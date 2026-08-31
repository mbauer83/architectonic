// @vitest-environment jsdom
//
// What the panel puts on screen for a diagram that offers only some of its controls.
//
// The helpers tests cover each decision on its own; this one covers the template's arrangement of
// them, which is where both defects here lived. A legend control nested inside the attribute check
// is withheld from exactly the diagrams that have notation and no attributes, and no test of either
// decision alone can see it.

import { describe, expect, it } from 'vitest'
import { createApp, h, type App } from 'vue'
import DiagramReadingPanel from '../DiagramReadingPanel.vue'
import { EMPTY_READING_LENS, type ReadingLens } from '../../../domain/readingLens'
import type { AttributeOffer, DiagramAttributePanel, TypeOffer } from '../../../domain/schemas/diagrams'

const attribute: AttributeOffer = {
  name: 'risk_score', declared_type: 'integer', colour: 'ramp', values: [], present_on: 4,
}

const typeOffer: TypeOffer = {
  entity_type: 'application-component', specialization: '', drawn: 4, attributes: [attribute],
}

const panel = (over: Partial<DiagramAttributePanel> = {}): DiagramAttributePanel => ({
  shared: [], types: [], disputed: [], drawn: 0, can_explain_notation: false, ...over,
})

/** Mount the panel with its fold open, and return the text and the controls a reader would see. */
const opened = (
  offer: DiagramAttributePanel, lens: ReadingLens = EMPTY_READING_LENS,
): { text: string; labels: string[]; kinds: string[]; app: App } => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({
    render: () => h(DiagramReadingPanel, { panel: offer, lens }),
  })
  app.mount(host)
  host.querySelector<HTMLButtonElement>('.reading__toggle')?.click()
  return {
    get text() { return host.textContent ?? '' },
    get labels() {
      return [...host.querySelectorAll('input[type=checkbox]')]
        .map((box) => (box.closest('label')?.textContent ?? '').trim())
    },
    get kinds() {
      return [...host.querySelectorAll('.kinds__choice')].map((b) => (b.textContent ?? '').trim())
    },
    app,
  }
}

describe('a diagram whose types declare no attributes', () => {
  it('is still offered the legend, because notation and attributes are independent', async () => {
    const view = opened(panel({ drawn: 13, can_explain_notation: true }))
    await Promise.resolve()

    expect(view.labels).toEqual(['Explain the notation, in the image'])
    view.app.unmount()
  })

  it('says the entities it draws declare nothing, not that it draws nothing', async () => {
    const view = opened(panel({ drawn: 13, can_explain_notation: true }))
    await Promise.resolve()

    expect(view.text).toContain('The 13 entities this diagram draws declare no attributes')
    expect(view.text).not.toContain('draws no model entities')
    view.app.unmount()
  })

  it('says it draws nothing only when it draws nothing', async () => {
    const view = opened(panel({ drawn: 0, can_explain_notation: true }))
    await Promise.resolve()

    expect(view.text).toContain('This diagram draws no model entities')
    view.app.unmount()
  })

  it('counts one entity in the singular', async () => {
    const view = opened(panel({ drawn: 1, can_explain_notation: true }))
    await Promise.resolve()

    expect(view.text).toContain('The 1 entity this diagram draws declare')
    view.app.unmount()
  })
})

describe('a diagram with attributes', () => {
  it('offers the attribute rows and no empty-state message', async () => {
    const view = opened(panel({ drawn: 4, types: [typeOffer] }))
    await Promise.resolve()

    expect(view.text).not.toContain('nothing to colour or print')
    expect(view.text).toContain('application-component')
    view.app.unmount()
  })

  it('offers no legend control where there is no notation to explain', async () => {
    const view = opened(panel({ drawn: 4, types: [typeOffer] }))
    await Promise.resolve()

    expect(view.labels).not.toContain('Explain the notation, in the image')
    view.app.unmount()
  })
})

describe('what happens to the element-kind colours', () => {
  // A diagram-level control, like the legend, because there is one colouring at a time: what becomes
  // of the element-kind colours is a fact about the picture rather than about an attribute. It lived
  // on the attribute row first, where a reader could reasonably ask which attribute's copy won.
  const withAttributes = panel({ drawn: 4, types: [typeOffer] })

  it('is not offered while nothing is being coloured by', async () => {
    // With no attribute colouring there is nothing to make room for, and removing the kind colours
    // would leave every element the same neutral — a blank diagram, not a clearer one.
    const view = opened(withAttributes)
    await Promise.resolve()

    expect(view.kinds).toEqual([])
    view.app.unmount()
  })

  it('is offered once, at the panel level, as soon as a colouring is on', async () => {
    const view = opened(withAttributes, { ...EMPTY_READING_LENS, colourBy: 'risk_score' })
    await Promise.resolve()

    expect(view.kinds).toEqual(['Keep', 'Remove'])
    view.app.unmount()
  })

  it('shows which treatment is in effect', async () => {
    const view = opened(
      withAttributes,
      { ...EMPTY_READING_LENS, colourBy: 'risk_score', elementKindColouring: 'drop' },
    )
    await Promise.resolve()

    const pressed = [...document.querySelectorAll('.kinds__choice[aria-pressed=true]')]
      .map((b) => (b.textContent ?? '').trim())
    expect(pressed).toEqual(['Remove'])
    view.app.unmount()
  })
})
