/**
 * Which step leads the outline, and whether every declared step reaches it.
 *
 * The browser half of a cross-language conformance pair. The other half is
 * `tests/architecture/test_the_editor_and_the_renderer_agree_on_the_entry_step.py`, which runs these
 * same graphs through the server's `entry_step` and asserts the same answers.
 *
 * Two implementations of one rule in two languages that cannot call each other. The editor needs the
 * answer synchronously on every keystroke, so it cannot ask the server; and a diagram whose outline
 * disagrees with its picture is worse than either being wrong on its own, because the author edits
 * one and looks at the other.
 */

import { describe, expect, it } from 'vitest'
import shippedDeclarations from './fixtures/shippedActivityDeclarations.json'

import { flatToRich, getConns, REJOIN, richToFlat, type LocalConn } from '../activityStepGraph'

const step = (id: string, type = 'action') => ({ id, type, label: id })
const edge = (conn_type: string, source: string, target: string): LocalConn =>
  ({ id: `c-${source}-${target}`, conn_type, source, target })

/**
 * The graphs both languages are checked against, and the step each must lead with.
 *
 * If a sample changes here it must change in the Python half in the same commit.
 */
export const ROOT_SAMPLES: readonly {
  name: string
  entities: Record<string, unknown>
  connections: LocalConn[]
  root: string | null
}[] = [
  {
    name: 'a plain chain leads with the step nothing flows into',
    entities: { action: [step('a1'), step('a2')] },
    connections: [edge('step-flow', 'a1', 'a2')],
    root: 'a1',
  },
  {
    name: 'a decision does not make its own branches candidates',
    entities: { action: [step('start'), step('yes'), step('no')], decision: [step('d', 'decision')] },
    connections: [
      edge('step-flow', 'start', 'd'),
      edge('step-then', 'd', 'yes'),
      edge('step-else', 'd', 'no'),
    ],
    root: 'start',
  },
  {
    name: 'a retry loop entered from outside still leads with the step outside it',
    entities: {
      action: [step('start'), step('attempt'), step('wait'), step('done')],
      decision: [step('ok', 'decision')],
    },
    connections: [
      edge('step-flow', 'start', 'attempt'),
      edge('step-flow', 'attempt', 'ok'),
      edge('step-then', 'ok', 'done'),
      edge('step-else', 'ok', 'wait'),
      edge('step-flow', 'wait', 'attempt'),
    ],
    root: 'start',
  },
  {
    name: 'a diagram that is nothing but a loop leads with a step no branch enters',
    // Tier one finds nothing: every step here is reached from somewhere. This is the case that
    // showed an empty outline for a diagram the renderer draws in full.
    entities: {
      action: [step('attempt'), step('wait'), step('done')],
      decision: [step('ok', 'decision')],
    },
    connections: [
      edge('step-flow', 'attempt', 'ok'),
      edge('step-then', 'ok', 'done'),
      edge('step-else', 'ok', 'wait'),
      edge('step-flow', 'wait', 'attempt'),
    ],
    root: 'attempt',
  },
  {
    name: 'a closed ring leads with the first declared step',
    // Tiers one and two both find nothing — every step is both flowed into and branch-entered is
    // not true here, but every step is flowed into. The third tier is what keeps an outline at all.
    entities: { action: [step('a'), step('b')] },
    connections: [edge('step-flow', 'a', 'b'), edge('step-flow', 'b', 'a')],
    root: 'a',
  },
]

describe('the step the outline leads with', () => {
  for (const sample of ROOT_SAMPLES) {
    it(sample.name, () => {
      const rich = flatToRich({ ...sample.entities, _connections: sample.connections })

      expect(rich.steps.length).toBeGreaterThan(0)
      expect(rich.steps[0].id).toBe(sample.root)
    })
  }
})

describe('what the outline holds', () => {
  it('shows the steps of a diagram that is nothing but a loop', () => {
    // The defect: every step is branch-owned, so the "unowned steps" fallback produced an empty
    // outline. An author saw no steps at all and could have saved that emptiness over the diagram.
    const sample = ROOT_SAMPLES[3]

    const rich = flatToRich({ ...sample.entities, _connections: sample.connections })

    expect(rich.steps).not.toEqual([])
  })

  it('draws each declared step of a loop somewhere in the outline', () => {
    const sample = ROOT_SAMPLES[3]

    const rich = flatToRich({ ...sample.entities, _connections: sample.connections })
    const seen = new Set<string>()
    const walk = (steps: readonly { id: string; [k: string]: unknown }[]) => {
      for (const s of steps) {
        seen.add(s.id)
        for (const key of ['then_steps', 'else_steps', 'steps'])
          if (Array.isArray(s[key])) walk(s[key] as { id: string }[])
        if (Array.isArray(s.branches)) for (const b of s.branches as { id: string }[][]) walk(b)
      }
    }
    walk(rich.steps)

    expect([...seen].sort()).toEqual(['attempt', 'done', 'ok', 'wait'])
  })

  it('terminates on a closed ring rather than looping forever', () => {
    const sample = ROOT_SAMPLES[4]

    const rich = flatToRich({ ...sample.entities, _connections: sample.connections })

    expect(rich.steps.map(s => s.id)).toEqual(['a', 'b'])
  })
})

describe('the round trip through the editor', () => {
  /**
   * Read the flat form into an outline and write it straight back, changing nothing.
   *
   * The rule this project states for a syntax it both writes and reads: test the *pair*, asserting
   * they agree. Reading alone looked right — the outline held every step — while the write dropped
   * the one edge that made it a loop, and no test of either side could see it.
   */
  const roundTrip = (data: Record<string, unknown>) => {
    const rich = flatToRich(data)
    return richToFlat(rich.lanes, rich.steps, getConns(data))
  }

  const structuralEdges = (data: Record<string, unknown>) =>
    getConns(data)
      .filter(c => c.conn_type.startsWith('step-'))
      .map(c => `${c.conn_type} ${c.source}->${c.target}`)
      .sort()

  it('keeps the returning flow that makes a retry loop a loop', () => {
    const before = { ...ROOT_SAMPLES[2].entities, _connections: ROOT_SAMPLES[2].connections }

    const after = roundTrip(before)

    expect(structuralEdges(after)).toContain('step-flow wait->attempt')
  })

  it('keeps every declared step edge, and invents none', () => {
    const before = { ...ROOT_SAMPLES[2].entities, _connections: ROOT_SAMPLES[2].connections }

    const after = roundTrip(before)

    expect(structuralEdges(after)).toEqual(structuralEdges(before))
  })

  it('keeps every declared step', () => {
    const before = { ...ROOT_SAMPLES[2].entities, _connections: ROOT_SAMPLES[2].connections }

    const after = roundTrip(before)

    const ids = (d: Record<string, unknown>) =>
      ['action', 'decision', 'fork', 'partition']
        .flatMap(k => (Array.isArray(d[k]) ? (d[k] as { id: string }[]) : []))
        .map(s => s.id)
        .sort()
    expect(ids(after)).toEqual(ids(before))
  })

  it('writes back no field the outline invented', () => {
    // `returns_to` is the outline saying "this chain goes back up there". It is a fact about the
    // shape of the tree, not a property of the step, and writing it into the model would put a key
    // in `diagram-entities` that nothing reads and the schema does not declare.
    const before = { ...ROOT_SAMPLES[2].entities, _connections: ROOT_SAMPLES[2].connections }

    const after = roundTrip(before)

    const steps = ['action', 'decision'].flatMap(
      k => (Array.isArray(after[k]) ? (after[k] as Record<string, unknown>[]) : []),
    )
    expect(steps.filter(s => 'returns_to' in s)).toEqual([])
  })
})

describe('the round trip over the diagrams this repository actually ships', () => {
  /**
   * Fixtures the test owns are where exact assertions belong, and they are also where a translation
   * can be correct about cases nobody draws. These are the real declarations, lifted from the two
   * stored activity diagrams, so the round trip is stated over content the product has to survive.
   *
   * Counts are deliberately not asserted: authoring a step is the product working. What is asserted
   * is the invariant — read it, write it back unchanged, and nothing has moved.
   */
  const shipped: Record<string, Record<string, unknown>> = shippedDeclarations

  const roundTrip = (data: Record<string, unknown>) => {
    const rich = flatToRich(data)
    return richToFlat(rich.lanes, rich.steps, getConns(data))
  }

  const structuralEdges = (data: Record<string, unknown>) =>
    getConns(data)
      .filter(c => c.conn_type.startsWith('step-') && c.conn_type !== 'step-note-of')
      .map(c => `${c.conn_type} ${c.source}->${c.target}`)
      .sort()

  const stepIds = (data: Record<string, unknown>) =>
    ['action', 'decision', 'fork', 'partition']
      .flatMap(k => (Array.isArray(data[k]) ? (data[k] as { id: string }[]) : []))
      .map(s => s.id)
      .sort()

  for (const [name, data] of Object.entries(shipped)) {
    it(`keeps every step of ${name}`, () => {
      expect(stepIds(roundTrip(data))).toEqual(stepIds(data))
    })

    it(`keeps every structural edge of ${name}, and invents none`, () => {
      expect(structuralEdges(roundTrip(data))).toEqual(structuralEdges(data))
    })

    it(`draws every declared step somewhere in the outline of ${name}`, () => {
      const rich = flatToRich(data)
      const seen = new Set<string>()
      const walk = (steps: readonly { id: string; [k: string]: unknown }[]) => {
        for (const s of steps) {
          seen.add(s.id)
          for (const key of ['then_steps', 'else_steps', 'steps'])
            if (Array.isArray(s[key])) walk(s[key] as { id: string }[])
          if (Array.isArray(s.branches)) for (const b of s.branches as { id: string }[][]) walk(b)
        }
      }
      walk(rich.steps)

      expect([...seen].sort()).toEqual(stepIds(data))
    })
  }
})


describe('two branches that converge on one step', () => {
  /**
   * Ordinary in a real diagram, and a tree has nowhere to put the second arrival. Both ways of
   * getting it wrong were measured on the shipped scratchpad diagram, where a decision's else-arm and
   * another decision's then-arm both reach `a_select`:
   *
   * - placing the step in both arms wrote it into `diagram-entities` **twice** — fourteen placements
   *   for thirteen steps — so a save duplicated a step in the model;
   * - placing it once and saying nothing dropped one of its two entry edges, so a save deleted a
   *   branch of the flow.
   *
   * The marker is neither. The step is written once, and both edges that reach it are written.
   */
  const converging = {
    action: [step('start'), step('shared'), step('other')],
    decision: [step('d1', 'decision'), step('d2', 'decision')],
    _connections: [
      edge('step-flow', 'start', 'd1'),
      edge('step-then', 'd1', 'shared'),
      edge('step-else', 'd1', 'd2'),
      edge('step-then', 'd2', 'shared'),
      edge('step-else', 'd2', 'other'),
    ],
  }

  it('places the converged step once, not once per arm', () => {
    const rich = flatToRich(converging)
    const realSteps: string[] = []
    const walk = (steps: readonly { id: string; type: string; [k: string]: unknown }[]) => {
      for (const s of steps) {
        if (s.type !== REJOIN) realSteps.push(s.id)
        for (const key of ['then_steps', 'else_steps', 'steps'])
          if (Array.isArray(s[key])) walk(s[key] as { id: string; type: string }[])
      }
    }
    walk(rich.steps)

    expect(realSteps.filter(id => id === 'shared')).toEqual(['shared'])
  })

  it('marks the second arrival as a rejoin rather than dropping the arm', () => {
    const rich = flatToRich(converging)
    const d1 = rich.steps.find(s => s.id === 'd1')
    const d2 = (d1?.else_steps as Record<string, unknown>[])[0]

    expect((d2.then_steps as { id: string; type: string }[])[0])
      .toMatchObject({ id: 'shared', type: REJOIN })
  })

  it('writes both edges that reach the converged step', () => {
    const after = richToFlat(
      flatToRich(converging).lanes, flatToRich(converging).steps, getConns(converging),
    )
    const edges = getConns(after).map(c => `${c.conn_type} ${c.source}->${c.target}`).sort()

    expect(edges).toContain('step-then d1->shared')
    expect(edges).toContain('step-then d2->shared')
  })

  it('writes the converged step into the model exactly once', () => {
    const after = richToFlat(
      flatToRich(converging).lanes, flatToRich(converging).steps, getConns(converging),
    )

    expect((after.action as { id: string }[]).filter(s => s.id === 'shared')).toHaveLength(1)
  })

  it('never writes a rejoin marker into the model as a step', () => {
    const after = richToFlat(
      flatToRich(converging).lanes, flatToRich(converging).steps, getConns(converging),
    )
    const written = ['action', 'decision', 'fork', 'partition'].flatMap(
      k => (Array.isArray(after[k]) ? (after[k] as { type: string }[]) : []),
    )

    expect(written.filter(s => s.type === REJOIN)).toEqual([])
  })
})
