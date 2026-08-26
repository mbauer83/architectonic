/**
 * Whether a diagram's reading controls are offered at all.
 *
 * Some diagrams permit no reading: an activity diagram draws steps, whose types declare no
 * attributes, and its body carries none of the notation a legend explains. The panel there was a
 * header, dead checkboxes and a sentence saying there was nothing to do — so the question the view
 * asks is whether the offer holds anything, and it is answered here rather than in the template,
 * because "nothing to offer" is four conditions and a template that spelled them would drift from
 * the one that decides what to draw inside.
 */

import { Effect } from 'effect'
import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { ModelService } from '../../../application/ModelService'
import type { AttributeOffer, DiagramAttributePanel } from '../../../domain/schemas/diagrams'
import { useDiagramReadingLens } from '../useDiagramReadingLens'

const panel = (overrides: Partial<DiagramAttributePanel> = {}): DiagramAttributePanel => ({
  shared: [],
  types: [],
  disputed: [],
  drawn: 0,
  can_explain_notation: false,
  ...overrides,
})

const riskScore: AttributeOffer = {
  name: 'risk_score', declared_type: 'integer', colour: 'ramp', values: [], present_on: 9,
}

const lifecycleState: AttributeOffer = {
  name: 'lifecycle_state', declared_type: 'string', colour: 'palette',
  values: ['active', 'retired'], present_on: 8,
}

const readingOf = async (answer: DiagramAttributePanel) => {
  const svc = {
    getDiagramSvg: vi.fn(() => Effect.succeed('<svg/>')),
    getDiagramAttributePanel: vi.fn(() => Effect.succeed(answer)),
  } as unknown as ModelService
  const reading = useDiagramReadingLens({
    svc,
    diagramId: computed(() => 'ACT@1.a.some-flow'),
    drawn: () => true,
  })
  reading.begin()
  await Promise.resolve()
  await Promise.resolve()
  return reading
}

describe('whether a diagram offers a reading', () => {
  it('offers nothing before the answer has arrived', () => {
    const svc = {
      getDiagramSvg: vi.fn(() => Effect.succeed('<svg/>')),
      getDiagramAttributePanel: vi.fn(() => Effect.never),
    } as unknown as ModelService
    const reading = useDiagramReadingLens({
      svc,
      diagramId: computed(() => 'ARC@1.a.a-view'),
      drawn: () => true,
    })
    reading.begin()
    expect(reading.offersAnything.value).toBe(false)
  })

  it('offers nothing where no type declares an attribute and the notation cannot be explained', async () => {
    const reading = await readingOf(panel({ drawn: 7 }))
    expect(reading.panel.value?.drawn).toBe(7)
    expect(reading.offersAnything.value).toBe(false)
  })

  it('offers a reading for the legend alone, even where nothing can be coloured', async () => {
    const reading = await readingOf(panel({ drawn: 13, can_explain_notation: true }))
    expect(reading.offersAnything.value).toBe(true)
  })

  it('offers a reading for an attribute a type declares', async () => {
    const reading = await readingOf(panel({
      drawn: 9,
      types: [{
        entity_type: 'application_component',
        specialization: '',
        drawn: 9,
        attributes: [riskScore],
      }],
    }))
    expect(reading.offersAnything.value).toBe(true)
  })

  it('reads the type rows alone, which is what shared and disputed are derived from', async () => {
    // `shared` and `disputed` are grouped out of the type rows on the server, so neither can arrive
    // without them — pinned there by `test_nothing_reads_across_a_diagram_with_no_type_rows`. That is
    // what lets this be one condition instead of four, and the four disagreed on the impossible case.
    const reading = await readingOf(panel({
      drawn: 8,
      types: [{
        entity_type: 'application_component',
        specialization: '',
        drawn: 8,
        attributes: [lifecycleState],
      }],
      shared: [{ attribute: lifecycleState, on_rows: ['application_component', 'node'] }],
      disputed: ['owner'],
    }))
    expect(reading.offersAnything.value).toBe(true)
  })
})
