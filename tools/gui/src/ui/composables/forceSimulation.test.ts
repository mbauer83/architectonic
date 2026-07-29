/**
 * The cooling schedule's contract: a run always stops, and stopping does not depend on the
 * arrangement happening to balance.
 *
 * Force-mode expansion used to be applied between two paints — the canvas was hidden, the
 * whole simulation was driven to rest in one frame, and it reappeared already rearranged.
 * That was bought to prevent drift: the loop it replaced ran until nothing was moving much,
 * which is not a termination proof, because a graph whose forces balance can orbit forever.
 *
 * Cooling buys termination without buying it with invisibility, so these tests hold the
 * property the synchronous settle was there for. If a future change reintroduces an
 * unbounded run, the bounded-step tests below fail rather than the defect resurfacing as an
 * animation that never stops.
 */
import { describe, expect, it } from 'vitest'
import {
  ALPHA_HOT, COOLING_TICKS, FORCE_DEFAULTS, coolerAlpha, isCold, simulationStep,
  type ForceOptions, type SimBody, type SimLink,
} from './forceSimulation'

const CENTRE = { x: 600, y: 400 }

const body = (id: string, x: number, y: number, over: Partial<SimBody> = {}): SimBody =>
  ({ id, x, y, vx: 0, vy: 0, pinned: false, expanded: false, ...over })

/** Drive a run to its end, returning how many steps it took. Fails the bound rather than
 *  looping forever if the schedule ever stops terminating. */
const runToRest = (bodies: SimBody[], links: SimLink[] = [], limit = COOLING_TICKS * 4): number => {
  let alpha = ALPHA_HOT
  for (let step = 1; step <= limit; step++) {
    const moving = simulationStep(bodies, links, FORCE_DEFAULTS, CENTRE, alpha)
    alpha = coolerAlpha(alpha)
    if (!moving || isCold(alpha)) return step
  }
  return limit + 1
}

describe('the cooling schedule', () => {
  it('goes cold within its advertised step budget, whatever the forces are doing', () => {
    let alpha = ALPHA_HOT
    let steps = 0
    while (!isCold(alpha)) {
      alpha = coolerAlpha(alpha)
      steps += 1
    }

    expect(steps).toBeLessThanOrEqual(COOLING_TICKS)
  })

  it('cools monotonically, so no step can reheat the run', () => {
    let alpha = ALPHA_HOT
    for (let i = 0; i < 50; i++) {
      const next = coolerAlpha(alpha)
      expect(next).toBeLessThan(alpha)
      alpha = next
    }
  })
})

describe('a simulation run', () => {
  it('terminates on a population whose forces never settle on their own', () => {
    // A symmetric ring: every body is pushed equally by its neighbours, which is exactly the
    // arrangement that can trade energy back and forth indefinitely under a
    // "stop when nothing is moving" rule.
    const ring = Array.from({ length: 8 }, (_, i) =>
      body(`n${i}`, CENTRE.x + Math.cos((i / 8) * Math.PI * 2) * 200,
        CENTRE.y + Math.sin((i / 8) * Math.PI * 2) * 200))
    const links = ring.map((_, i) => ({ source: `n${i}`, target: `n${(i + 1) % 8}` }))

    expect(runToRest(ring, links)).toBeLessThanOrEqual(COOLING_TICKS)
  })

  it('comes to rest and stays there once cold', () => {
    // The anti-drift assertion. Not "the graph reached equilibrium" — a cooled run ends cold,
    // which is close to but not the same as balanced — but "once the run is over, continuing
    // to step it moves nothing". That is what stops the graph sliding away under the pointer.
    const bodies = [body('a', 400, 300), body('b', 800, 500), body('c', 620, 380)]
    const links: SimLink[] = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }]
    runToRest(bodies, links)

    const rested = bodies.map((b) => ({ x: b.x, y: b.y }))
    let alpha = 0
    for (let i = 0; i < 200; i++) {
      simulationStep(bodies, links, FORCE_DEFAULTS, CENTRE, alpha)
      alpha = coolerAlpha(alpha)
    }

    // Sub-pixel, not exactly zero: a run ends with a trace of velocity still damping out.
    // The claim is that nothing *visibly* moves, which is the claim the reader cares about.
    const drift = Math.max(...bodies.map((b, i) =>
      Math.hypot(b.x - rested[i].x, b.y - rested[i].y)))

    expect(drift).toBeLessThan(1)
  })

  it('keeps a freshly seeded neighbourhood on the canvas instead of flinging it away', () => {
    /*
     * The regression this suite originally missed.
     *
     * Every other test here asked whether the run *stops*. It does — and it did then too,
     * while leaving nodes seventy thousand pixels from the centre, because repulsion goes as
     * 1/d² and the bodies start nearly coincident: one enormous kick, then the cooling went
     * cold long before the springs could pull them back. Fitting the graph to include the
     * strays shrank everything else to specks.
     *
     * "It reached a fixed point" was true and useless. The property worth holding is that it
     * reaches a *sensible* one, so this bounds where the run is allowed to end.
     */
    const parent = body('p', CENTRE.x, CENTRE.y, { expanded: true })
    const kids = Array.from({ length: 14 }, (_, i) =>
      body(`k${i}`, CENTRE.x + Math.cos(i) * 0.5, CENTRE.y + Math.sin(i) * 0.5, { addedBy: 'p' }))
    const bodies = [parent, ...kids]

    runToRest(bodies, kids.map((k) => ({ source: 'p', target: k.id })))

    const furthest = Math.max(...bodies.map((b) => Math.hypot(b.x - CENTRE.x, b.y - CENTRE.y)))
    expect(furthest).toBeLessThan(FORCE_DEFAULTS.idealDist * 6)
  })

  it('never moves a pinned body, however hard it is pushed', () => {
    const held = body('held', CENTRE.x, CENTRE.y, { pinned: true })
    // Crowded right on top of it, so the repulsion term is at its largest.
    const crowd = Array.from({ length: 6 }, (_, i) => body(`n${i}`, CENTRE.x + i, CENTRE.y + i))

    runToRest([held, ...crowd])

    expect({ x: held.x, y: held.y }).toEqual({ x: CENTRE.x, y: CENTRE.y })
  })
})

describe('an expanded node', () => {
  const IDEAL = FORCE_DEFAULTS.idealDist

  /**
   * Where the parent→child spring alone comes to rest.
   *
   * Repulsion and centre gravity are switched off so this measures the rest length the spring
   * states, not where a whole population happens to balance. Asserted at the force law rather
   * than by settling a run, because a cooled run ends *cold* rather than at equilibrium — it
   * stops short of the rest length, so a settling test would measure the schedule, not the rule.
   */
  const springOnly: ForceOptions = { ...FORCE_DEFAULTS, repulsion: 0, centerPull: 0 }

  /** How far the child moves in one step when held `gap` from its parent. Positive is outward. */
  const driftAt = (gap: number, expanded: boolean): number => {
    const parent = body('parent', CENTRE.x, CENTRE.y, { pinned: true })
    const child = body('child', CENTRE.x + gap, CENTRE.y, { expanded, addedBy: 'parent' })
    simulationStep([parent, child], [{ source: 'parent', target: 'child' }], springOnly, CENTRE, 1)
    return child.x - (CENTRE.x + gap)
  }

  it('rests at twice the neighbour distance plus a buffer', () => {
    // Its own neighbours settle roughly one idealDist beyond it, so anything short of twice
    // the distance puts the two neighbourhoods on top of each other.
    expect(driftAt(IDEAL * 2 + 120, true)).toBeCloseTo(0, 6)
  })

  it('is still being pushed outward at exactly twice the distance', () => {
    // At exactly 2x the parent's ring and the child's ring are tangent and their nodes
    // interleave. The buffer is what separates them, so the spring must not rest here.
    expect(driftAt(IDEAL * 2, true)).toBeGreaterThan(0)
  })

  it('leaves an unexpanded sibling at the plain neighbour distance', () => {
    expect(driftAt(IDEAL, false)).toBeCloseTo(0, 6)
    // …and an unexpanded node that far out is pulled back in, rather than sharing the ring.
    expect(driftAt(IDEAL * 2 + 120, false)).toBeLessThan(0)
  })

  it('settles further from its parent than an unexpanded sibling does', () => {
    // The whole-population check behind the force law: with every force in play and a real
    // cooled run, expanding a node still visibly moves it out.
    const gapAfterRun = (expanded: boolean): number => {
      const parent = body('parent', CENTRE.x, CENTRE.y, { pinned: true })
      const child = body('child', CENTRE.x + IDEAL, CENTRE.y, { expanded, addedBy: 'parent' })
      runToRest([parent, child], [{ source: 'parent', target: 'child' }])
      return Math.hypot(child.x - parent.x, child.y - parent.y)
    }

    expect(gapAfterRun(true)).toBeGreaterThan(gapAfterRun(false))
  })
})

describe('expanding a neighbour', () => {
  /**
   * The shape that motivated all of this: an anchor with a first hop, one of whose members has
   * been expanded and carries a neighbourhood of its own.
   *
   * Asserted after a *cooled* run, not at equilibrium, because the run is what the user sees.
   * A schedule that stops halfway leaves the two neighbourhoods interleaved even though the
   * forces describe them as separate — which is exactly what "the clusters do not separate"
   * turned out to be, and what no test here caught until it was reported twice.
   */
  const walk = () => {
    const anchor = body('A', CENTRE.x, CENTRE.y)
    const hop1 = Array.from({ length: 6 }, (_, i) =>
      body(`h${i}`, CENTRE.x + Math.cos(i) * 250, CENTRE.y + Math.sin(i) * 250, { addedBy: 'A' }))
    hop1[0].expanded = true
    // Seeded almost on top of their parent, as a fresh expansion really does seed them.
    const hop2 = Array.from({ length: 10 }, (_, i) =>
      body(`g${i}`, hop1[0].x + Math.cos(i) * 2, hop1[0].y + Math.sin(i) * 2, { addedBy: 'h0' }))
    const bodies = [anchor, ...hop1, ...hop2]
    runToRest(bodies, [
      ...hop1.map((h) => ({ source: 'A', target: h.id })),
      ...hop2.map((g) => ({ source: 'h0', target: g.id })),
    ])
    const gap = (a: SimBody, b: SimBody) => Math.hypot(a.x - b.x, a.y - b.y)
    const minGap = (xs: SimBody[], ys: SimBody[]) =>
      Math.min(...xs.flatMap((x) => ys.map((y) => gap(x, y))))
    return {
      parentGap: gap(anchor, hop1[0]),
      crossNeighbourhood: minGap(hop1.slice(1), hop2),
      withinNeighbourhood: Math.min(...hop2.flatMap((a, i) => hop2.slice(i + 1).map((b) => gap(a, b)))),
    }
  }

  it('carries the expanded node most of the way to its stated distance', () => {
    // Most of the way, not all: a cooled run ends cold rather than balanced. What matters is
    // that it lands nearer the rest length than the plain neighbour distance it started from.
    const { parentGap } = walk()

    expect(parentGap).toBeGreaterThan(FORCE_DEFAULTS.idealDist * 2)
  })

  it('leaves the two neighbourhoods clearly apart, not interleaved', () => {
    const { crossNeighbourhood, withinNeighbourhood } = walk()

    // The separation is what makes them read as two clusters: members of different
    // neighbourhoods must end up markedly further apart than members of the same one.
    expect(crossNeighbourhood).toBeGreaterThan(withinNeighbourhood * 1.8)
  })
})

describe('alpha', () => {
  it('scales how fast the graph converges, not what it converges on', () => {
    // Held at a constant temperature the simulation settles where the net force is zero, and
    // no uniform scaling of the forces can move that point. This is why turning alpha down to
    // animate cannot quietly produce a different arrangement than running the graph hot.
    //
    // Constant alpha, deliberately: a *cooled* run stops when it goes cold rather than when it
    // balances, so comparing two cooled runs would compare where each ran out of heat.
    const equilibrium = (alpha: number): Array<{ x: number; y: number }> => {
      const bodies = [body('a', 300, 300), body('b', 900, 500), body('c', 610, 390)]
      const links: SimLink[] = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }]
      for (let i = 0; i < 20_000; i++) simulationStep(bodies, links, FORCE_DEFAULTS, CENTRE, alpha)
      return bodies.map((b) => ({ x: b.x, y: b.y }))
    }

    const hot = equilibrium(1)
    const gentle = equilibrium(0.25)

    // Within a couple of pixels, not bit-identical: the two runs approach the same point at
    // different rates, so after a fixed number of steps each is a hair short of it.
    const apart = Math.max(...hot.map((p, i) => Math.hypot(p.x - gentle[i].x, p.y - gentle[i].y)))

    expect(apart).toBeLessThan(2)
  })
})
