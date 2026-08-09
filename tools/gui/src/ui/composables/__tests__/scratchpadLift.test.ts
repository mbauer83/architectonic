/**
 * Planning a lift, then performing the same one.
 *
 * The property worth a test is that the *second* call carries the selection the *first* was planned
 * for. A dialog that re-derives its selection on confirm would execute something other than what
 * was read, and the difference would be invisible — the plan on screen would still look right.
 */

import { Effect } from 'effect'
import { describe, expect, it, vi } from 'vitest'
import type { ModelService } from '../../../application/ModelService'
import type { Scratchpad, ScratchpadLift } from '../../../domain/schemas/scratchpads'
import { useScratchpadLift } from '../useScratchpadLift'

const plan = (overrides: Partial<ScratchpadLift> = {}): ScratchpadLift => ({
  targets: [],
  items: [],
  refusal: '',
  blocks: false,
  'dry-run': true,
  committed: false,
  'operation-id': '',
  ...overrides,
})

const scratchpad = (): Scratchpad => ({
  'artifact-id': 'SCR@1.a.pad',
  'artifact-type': 'scratchpad',
  name: 'Pad',
  description: '',
  version: '0.1.4',
  status: 'draft',
  group: 'strategy-and-value',
  'meta-ontology': 'archimate-4',
  notes: [
    { id: 'n1', title: 'One', body: '', destination: 'undecided', area: 'unfiled' },
    { id: 'n2', title: 'Two', body: '', destination: 'undecided', area: 'unfiled' },
  ],
  links: [],
  areas: [],
  layout: {},
})

const serviceWith = (lifts: ScratchpadLift[]) => {
  const calls: unknown[] = []
  const service = {
    liftScratchpad: (_id: string, body: unknown) => {
      calls.push(body)
      return Effect.succeed(lifts[calls.length - 1] ?? lifts[lifts.length - 1])
    },
    listGroups: () => Effect.succeed({}),
  } as unknown as ModelService
  return { service, calls }
}

describe('lifting from the canvas', () => {
  it('plans the selection it was given, and never writes on the preflight', async () => {
    const { service, calls } = serviceWith([plan()])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, scratchpad, () => {})

    await lift.preflight(['n1'])

    expect(lift.open.value).toBe(true)
    expect(calls).toEqual([
      { version: '0.1.4', selection: ['n1'], targets: {}, draw: false, 'dry-run': true },
    ])
  })

  it('reads an empty selection as everything, rather than sending one the server refuses', async () => {
    // The server refuses an empty selection deliberately: a mis-click must not lift a whole canvas.
    const { service, calls } = serviceWith([plan()])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, scratchpad, () => {})

    await lift.preflight([])

    expect((calls[0] as { selection: string[] }).selection).toEqual(['n1', 'n2'])
    expect(lift.selectionSize.value).toBe(2)
  })

  it('executes the selection it planned, not whatever is selected by then', async () => {
    const { service, calls } = serviceWith([plan(), plan({ committed: true, 'dry-run': false })])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, scratchpad, () => {})

    await lift.preflight(['n1'])
    await lift.lift()

    expect((calls[1] as { selection: string[]; 'dry-run': boolean })).toMatchObject({
      selection: ['n1'], 'dry-run': false,
    })
  })

  it('tells the view to reload once something was committed', async () => {
    const committed = vi.fn()
    const { service } = serviceWith([plan(), plan({ committed: true })])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, scratchpad, committed)

    await lift.preflight(['n1'])
    expect(committed).not.toHaveBeenCalled()

    await lift.lift()
    expect(committed).toHaveBeenCalledOnce()
  })

  it('closing forgets the plan, so the next open cannot show the last one', async () => {
    const { service } = serviceWith([plan()])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, scratchpad, () => {})

    await lift.preflight(['n1'])
    lift.close()

    expect(lift.open.value).toBe(false)
    expect(lift.plan.value).toBeNull()
  })
})

describe('choosing where each frame lands', () => {
  it('asks once per frame the selection spans, not once per frame the scratchpad has', async () => {
    const framed = (): Scratchpad => ({
      ...scratchpad(),
      areas: [
        { id: 'strategy', label: 'Vision & strategy' },
        { id: 'project', label: 'Project' },
        { id: 'enabling', label: 'Enabling' },
      ],
      notes: [
        { id: 'n1', title: 'One', body: '', destination: 'undecided', area: 'strategy' },
        { id: 'n2', title: 'Two', body: '', destination: 'undecided', area: 'project' },
      ],
    })
    const { service, calls } = serviceWith([plan()])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, framed, () => {})

    await lift.preflight([])
    expect(lift.frames.value.map((frame) => frame.id)).toEqual(['project', 'strategy'])

    lift.setTarget('project', 'q3-expansion')
    await lift.lift()

    expect((calls[1] as { targets: Record<string, string> }).targets)
      .toEqual({ project: 'q3-expansion' })
  })
})

describe('the view a lift may draw', () => {
  it('is off unless asked for, because a picture nobody asked for is a file nobody expected', async () => {
    const { service, calls } = serviceWith([plan(), plan({ committed: true })])
    const lift = useScratchpadLift(service, { value: 'SCR@1.a.pad' } as never, scratchpad, () => {})

    await lift.preflight(['n1'])
    expect((calls[0] as { draw: boolean }).draw).toBe(false)

    lift.draw.value = true
    await lift.lift()
    expect((calls[1] as { draw: boolean }).draw).toBe(true)
  })
})
