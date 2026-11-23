/**
 * Align and distribute, held to what the server's `layout_intents` answers for the same elements.
 *
 * `tests/fixtures/layout_geometry/intents.json` holds the cases and the Python answers; pytest holds
 * the file to the Python, and this holds `layoutIntents` to the file, to the pixel.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import type { AlignEdge, DistributeAxis } from '../layoutIntents'
import { aligned, distributed } from '../layoutIntents'

interface Case {
  name: string
  elements: Record<string, Extent>
  intent: { intent: 'align'; edge: AlignEdge } | { intent: 'distribute'; axis: DistributeAxis }
  to: Record<string, [number, number]>
}

const { cases } = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../../../../../tests/fixtures/layout_geometry/intents.json', import.meta.url)), 'utf-8',
  ),
) as { cases: Case[] }

describe('align and distribute, as the server compiles them', () => {
  it('has cases for every edge and both axes', () => {
    const kinds = new Set(cases.map(({ intent }) => (intent.intent === 'align' ? intent.edge : intent.axis)))
    expect([...kinds].sort()).toEqual(['bottom', 'centre_x', 'centre_y', 'left', 'right', 'top', 'x', 'y'])
  })

  it.each(cases.map((one) => [one.name, one] as const))('%s', (_name, one) => {
    const extents = new Map(Object.entries(one.elements))
    const answer = one.intent.intent === 'align'
      ? aligned(extents, one.intent.edge) : distributed(extents, one.intent.axis)
    expect(Object.fromEntries([...answer].map(([key, at]) => [key, [at.x, at.y]]))).toEqual(one.to)
  })

})
