/**
 * Named force-layout spacing settings.
 *
 * Each layout reads the rung in its own units — the force simulation's repulsion and rest length,
 * the radial layout's ring increment, the cluster layout's cell air — because "more spacious" is
 * one intention and three arrangements. Only the force pair used to be here, so asking for more
 * room while looking at a radial or clustered graph changed nothing at all.
 *
 * They carry no vocabulary from any module: a compact assurance graph and a compact architecture
 * graph are compact in exactly the same sense. They lived in the architecture view's helpers,
 * which meant the shared layout toolbar and the assurance explorer both had to import from a
 * module named after a surface neither of them is. That coupling is what this removes.
 */

export interface SpacingPreset {
  label: string
  /** Force layout: how hard bodies push apart, and where a spring rests. */
  repulsion: number
  idealDist: number
  /** Radial layout: the increment between hop rings. A ring crowded by its labels widens past it. */
  ringSpacing: number
  /**
   * How much of a ring member's own drawn width it is given as circumference.
   *
   * `1` separates every label completely, which is what a ring costs if nothing may touch: with
   * 27 members whose labels run to 200 units, that is a ring some 850 units across. It is the
   * right answer for the roomiest rung and much too much for the default one — a little overlap
   * between neighbouring labels is what ordinary density looks like, and was what the fixed arc
   * produced before labels were allowed their full width.
   */
  labelArc: number
  /** Cluster layout: how much air a cell gets beyond the extent of what it holds. */
  cellGap: number
}

/**
 * Repulsion runs four times what it did, at every rung.
 *
 * Measured on the first-hop graph the dogfood repository produces — 27 nodes, 92 edges — by
 * settling the real schedule from a fixed seed, counting straight-line edge crossings, and then
 * rescaling each result so its closest pair of nodes sits at one node-diameter: every arrangement
 * is read at the same node size, so the extent is honestly "how far must a reader zoom out".
 *
 * At `Normal` that is 592 crossings and a 1140 diagonal before, 464 and 979 after — fewer crossings
 * *and* less zoom-out, which is not the trade it looks like. Raw extent grows, but the whole
 * arrangement grows with it; what matters is the ratio, and the ratio improves.
 *
 * It also fixes something the old numbers were quietly failing at. The expanded-neighbourhood
 * spring asks for 620 units between a parent and an expanded child; at repulsion 3000 it settled at
 * 455, and the closest pair in that arrangement was 72 units — nearer than two 34-radius nodes can
 * be drawn without crowding. At 20000 they settle at 564 and 109.
 *
 * `idealDist` is unchanged, and deliberately so: raising it *adds* crossings (592 → 698 → 699 → 715
 * at 250 → 350 → 500 → 700). Longer springs do not untangle a dense graph, they let it tangle
 * further apart, which is why the ladder used to get worse as it got roomier.
 */
export const SPACING_PRESETS: readonly SpacingPreset[] = [
  { label: 'Compact', repulsion: 6000, idealDist: 150, ringSpacing: 120, cellGap: 0.6, labelArc: 0.4 },
  { label: 'Normal', repulsion: 20000, idealDist: 250, ringSpacing: 180, cellGap: 1, labelArc: 0.6 },
  { label: 'Spacious', repulsion: 40000, idealDist: 400, ringSpacing: 280, cellGap: 1.6, labelArc: 1 },
  { label: 'Very spacious', repulsion: 80000, idealDist: 600, ringSpacing: 400, cellGap: 2.4, labelArc: 1.4 },
]
