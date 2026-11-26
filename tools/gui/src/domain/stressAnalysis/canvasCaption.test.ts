import { describe, expect, it } from 'vitest'
import { type CanvasReading, canvasCaption, emptyCaption } from './canvasCaption'

const reading = (over: Partial<CanvasReading>): CanvasReading => ({
  tab: 'stressors', selected: null, judging: null, judgedName: '', judgedRead: false, ...over,
})
const QUEUED = { judging: 'CAND@1795686569.DdH9_2U.queued-promotions', judgedName: 'Queued promotions' }

describe('the stress workspace canvas caption', () => {
  it('names the adaptation being judged, once its picture is read', () => {
    const caption = canvasCaption(reading({ ...QUEUED, judgedRead: true }))
    expect(caption).toContain('Queued promotions, being judged')
    expect(caption).not.toContain('naive architecture, being judged')
  })

  it('names the adaptation being judged while its picture is still being read, not the naive', () => {
    const judged = reading({ ...QUEUED, judgedRead: false })
    expect(canvasCaption(judged)).toContain('Queued promotions, being judged')
    expect(canvasCaption(judged)).not.toContain('naive')
    expect(emptyCaption(judged)).toBe('Drawing Queued promotions…')
  })

  it('names the naive architecture and the integration when those are judged', () => {
    expect(canvasCaption(reading({ judging: 'naive' }))).toMatch(/^The naive architecture, being judged/)
    expect(canvasCaption(reading({ judging: 'integration' }))).toMatch(/^The integration is the model/)
    expect(emptyCaption(reading({ judging: 'naive' }))).toMatch(/^Nothing to draw yet/)
  })

  it('says what a press does on the Stressors tab', () => {
    expect(canvasCaption(reading({ selected: 'S1' }))).toMatch(/^Press an element to tick or untick it for S1/)
    expect(canvasCaption(reading({ tab: 'naive' }))).toMatch(/^Select a row or an element/)
  })
})
