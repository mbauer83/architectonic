/**
 * The force layout's physics: one pure step, and the cooling schedule that bounds a run.
 *
 * Kept free of Vue and of the graph composable's own state so the simulation can be reasoned
 * about — and tested — as what it is: a function from an arrangement to the next arrangement.
 * The bodies it moves are described structurally, so it names nothing about what a node
 * *means* on any particular graph surface.
 */

export interface ForceOptions {
  repulsion: number
  attraction: number
  idealDist: number
  centerPull: number
  damping: number
}

export const FORCE_DEFAULTS: ForceOptions = {
  repulsion: 3000,
  attraction: 0.005,
  idealDist: 250,
  centerPull: 0.0005,
  damping: 0.85,
}

/** A body the simulation moves. `expanded`/`addedBy` shape the forces; see below. */
export interface SimBody {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  pinned: boolean
  expanded: boolean
  addedBy?: string
}

export interface SimLink {
  source: string
  target: string
}

const MIN_VELOCITY = 0.01

/**
 * How far an expanded node is held from its own parent.
 *
 * An expanded node has acquired a neighbourhood of its own, and that neighbourhood needs room
 * that does not sit on top of its parent's. Twice the neighbour distance is the least that can
 * clear it — the expanded node's own neighbours settle roughly one `idealDist` further out
 * again — so at exactly 2× the two rings are tangent and their nodes interleave. The buffer is
 * the gap that makes them read as two clusters rather than one crowd.
 *
 * A rest length rather than a stronger force, deliberately: repulsion tuned to dominate the
 * equal-distance spring would have to out-pull it at every separation, which means it also
 * flings unexpanded siblings outward and fights the cooling schedule all the way down. Moving
 * the spring's rest length states the intended distance directly, and the same cooling that
 * settles everything else settles this too.
 */
const EXPANDED_SPRING_BUFFER = 120
const expandedSpringDist = (idealDist: number): number => idealDist * 2 + EXPANDED_SPRING_BUFFER

/**
 * Closest two bodies may be for the purpose of repulsion.
 *
 * Repulsion goes as 1/d², so without a floor two nearly-coincident nodes generate an
 * unbounded force. Freshly seeded neighbours *are* nearly coincident, so this is the normal
 * case, not a pathological one: at a 1px floor the pair got a ~3000-unit kick, damping carried
 * it thousands of pixels, and the cooling schedule went cold long before the springs could
 * haul them back — nodes stranded so far out that fitting the graph shrank everything else to
 * nothing. The floor is a node's own drawn extent: two nodes cannot be nearer than touching,
 * so pretending they can buys only the blow-up.
 */
const MIN_SEPARATION = 45

/**
 * Furthest a body may travel in one tick.
 *
 * A belt to `MIN_SEPARATION`'s braces, and the one that makes the run *unconditionally*
 * stable: whatever forces conspire, a body moves at most this far per tick, so it can never
 * cross the canvas between two frames and land somewhere the remaining schedule cannot
 * recover it from. Generous enough to be invisible in normal motion — over a full cooling run
 * it still permits several thousand pixels of honest travel.
 */
const MAX_STEP = 40

/**
 * How much harder nodes from different neighbourhoods push each other apart.
 *
 * Expanding a node should produce a visibly separate cluster, and the spring rest length alone
 * does not achieve that: it fixes the distance from parent to child, while the child's new
 * neighbours are free to drift back among the parent's own. Making the repulsion between
 * neighbourhoods dominate the equal-distance spring *within* one is what actually separates
 * them — the second of the two mechanisms available, and the one that keeps working as more
 * hops are opened.
 */
const CROSS_NEIGHBOURHOOD_REPULSION = 3.0

/**
 * Whether two bodies belong to the same neighbourhood: a parent and the nodes its expansion
 * added, and those nodes with each other. A node reached from two parents is filed under the
 * one that introduced it, which is an approximation — but it is the only parentage the graph
 * records, and it keeps the rule free of any vocabulary about what the nodes mean.
 */
const sameNeighbourhood = (a: SimBody, b: SimBody): boolean =>
  (a.addedBy !== undefined && a.addedBy === b.addedBy)
  || a.addedBy === b.id
  || b.addedBy === a.id

/**
 * Cooling schedule, after d3-force's `alpha` / `alphaDecay` / `alphaMin`.
 *
 * The simulation injects force on every step, so "nothing is moving much right now" is not a
 * proof that it will ever stop — a balanced graph can orbit indefinitely, and that drift is
 * what the old synchronous settle was bought to prevent. It bought it by never animating.
 *
 * Alpha scales the force applied each step and decays geometrically, so within COOLING_TICKS
 * no new energy enters and `damping` bleeds off what is left: a run provably terminates.
 *
 * Note what a run ends *at*. It ends cold, which is near the arrangement the forces are
 * pulling towards but is not the same claim as having reached equilibrium — a longer run
 * would still creep. That is deliberate: the guarantee being bought is that the graph stops,
 * not that it is optimal. Because the animated and synchronous drivers run the identical
 * schedule, they come to rest in the same place, which is the property that actually matters.
 */
export const COOLING_TICKS = 720
const ALPHA_MIN = 0.001
const ALPHA_DECAY = 1 - ALPHA_MIN ** (1 / COOLING_TICKS)

/**
 * Simulation steps run per animation frame.
 *
 * The budget above is a number of *steps*, not frames, and the two are deliberately decoupled.
 * At one step per frame a 180-step run animated in about three seconds but went cold roughly
 * halfway to the arrangement the forces describe — an expanded neighbourhood ended ~490px from
 * its parent instead of the 620 its spring specifies, and neighbourhoods that should have been
 * 357px apart froze 164px apart, which is what "the clusters do not separate" looked like.
 *
 * Lengthening the schedule in frames would have fixed the geometry by making the reader watch
 * a twelve-second animation. Running several steps per frame buys the same convergence in the
 * same three seconds: 720 steps over 180 frames.
 */
export const STEPS_PER_FRAME = 4

export const ALPHA_HOT = 1

/** The temperature after one step. */
export const coolerAlpha = (alpha: number): number => alpha * (1 - ALPHA_DECAY)

/** Whether the run has cooled far enough that no meaningful force is left to apply. */
export const isCold = (alpha: number): boolean => alpha < ALPHA_MIN

/**
 * Advance the arrangement one step in place, with every force scaled by `alpha`.
 *
 * Returns whether anything is still moving fast enough to be worth another step — an early
 * exit for an arrangement that is already at rest, not a termination guarantee. The guarantee
 * is the cooling schedule.
 */
export const simulationStep = (
  bodies: readonly SimBody[],
  links: readonly SimLink[],
  options: ForceOptions,
  centre: { x: number; y: number },
  alpha: number,
): boolean => {
  const { repulsion, attraction, idealDist, centerPull, damping } = options

  // Repulsion between all pairs; expanded cluster-centres repel each other extra.
  for (let i = 0; i < bodies.length; i++) {
    for (let j = i + 1; j < bodies.length; j++) {
      const a = bodies[i]
      const b = bodies[j]
      const dx = b.x - a.x
      const dy = b.y - a.y
      // Two distances: the real one, which gives the direction to push along, and the floored
      // one, which sets the magnitude. Dividing by the real distance for direction keeps the
      // unit vector honest even when the bodies are on top of each other.
      const raw = Math.max(Math.sqrt(dx * dx + dy * dy), 0.001)
      const dist = Math.max(raw, MIN_SEPARATION)
      const r = sameNeighbourhood(a, b) ? repulsion : repulsion * CROSS_NEIGHBOURHOOD_REPULSION
      const force = (r / (dist * dist)) * alpha
      const fx = (dx / raw) * force
      const fy = (dy / raw) * force
      if (!a.pinned) { a.vx -= fx; a.vy -= fy }
      if (!b.pinned) { b.vx += fx; b.vy += fy }
    }
  }

  // Attraction along links.
  // When the child side of a parent→child link is expanded, use a longer spring so the
  // sub-cluster moves away from the grandparent. Un-expanded siblings keep idealDist.
  // Multi-connected nodes settle at the geometric centre of their springs.
  const byId = new Map(bodies.map((b) => [b.id, b]))
  for (const link of links) {
    const src = byId.get(link.source)
    const tgt = byId.get(link.target)
    if (!src || !tgt) continue
    const child = src.addedBy === tgt.id ? src
      : tgt.addedBy === src.id ? tgt
      : null
    const springDist = child?.expanded ? expandedSpringDist(idealDist) : idealDist
    const dx = tgt.x - src.x
    const dy = tgt.y - src.y
    const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
    const force = (dist - springDist) * attraction * alpha
    const fx = (dx / dist) * force
    const fy = (dy / dist) * force
    if (!src.pinned) { src.vx += fx; src.vy += fy }
    if (!tgt.pinned) { tgt.vx -= fx; tgt.vy -= fy }
  }

  // Centre gravity, then integrate.
  let maxV = 0
  for (const body of bodies) {
    if (body.pinned) { body.vx = 0; body.vy = 0; continue }
    body.vx += (centre.x - body.x) * centerPull * alpha
    body.vy += (centre.y - body.y) * centerPull * alpha
    body.vx *= damping
    body.vy *= damping
    // Clamp the step, not the velocity components separately — scaling both by the same
    // factor preserves the direction the forces chose, where clamping each axis would bend
    // the motion towards the diagonal.
    const speed = Math.hypot(body.vx, body.vy)
    if (speed > MAX_STEP) {
      body.vx = (body.vx / speed) * MAX_STEP
      body.vy = (body.vy / speed) * MAX_STEP
    }
    body.x += body.vx
    body.y += body.vy
    maxV = Math.max(maxV, Math.abs(body.vx), Math.abs(body.vy))
  }
  return maxV > MIN_VELOCITY
}
