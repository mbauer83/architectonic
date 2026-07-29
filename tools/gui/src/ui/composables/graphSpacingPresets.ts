/**
 * Named force-layout spacing settings.
 *
 * These are parameters of the simulation — how hard nodes repel, how long a spring rests — and
 * carry no vocabulary from any module: a compact assurance graph and a compact architecture
 * graph are compact in exactly the same sense. They lived in the architecture view's helpers,
 * which meant the shared layout toolbar and the assurance explorer both had to import from a
 * module named after a surface neither of them is. That coupling is what this removes.
 */

export interface SpacingPreset {
  label: string
  repulsion: number
  idealDist: number
}

export const SPACING_PRESETS: readonly SpacingPreset[] = [
  { label: 'Compact', repulsion: 1500, idealDist: 150 },
  { label: 'Normal', repulsion: 3000, idealDist: 250 },
  { label: 'Spacious', repulsion: 6000, idealDist: 400 },
  { label: 'Very spacious', repulsion: 12000, idealDist: 600 },
]
