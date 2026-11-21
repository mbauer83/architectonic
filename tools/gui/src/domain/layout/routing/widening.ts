/**
 * Room for the lines, made once: the arrangement a first layout writes down, its narrow channels widened.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/widening.py`, for the canvas to call
 * when it first writes a diagram's layout down. Every coordinate past a too-narrow channel's near side
 * moves on by what the channel lacks: boxes beyond it move, boxes it runs through grow, elements move
 * whole. The routes are found again and the channels measured again, up to ROUNDS times.
 */
import type { Channel } from '../channels'
import { tooNarrow, widerBy } from '../channels'
import type { Extent, Point } from '../geometry'
import { routeAll } from './router'
import type { Connector, RoutingScene } from './scene'
import { runFor } from './scene'

/** How many times the routes are found again and the channels widened again. */
export const ROUNDS = 4

type Spread = (value: number) => number

const spreadOf = (cuts: ReadonlyMap<number, number>): Spread => {
  const sorted = [...cuts].sort(([one], [other]) => one - other)
  return (value) => {
    let moved = value
    for (const [at, room] of sorted) if (at < value) moved += room
    return moved
  }
}

const cutsOf = (narrow: readonly Channel[], across: 'x' | 'y'): Map<number, number> => {
  const cuts = new Map<number, number>()
  for (const channel of narrow) {
    if (channel.across === across) cuts.set(channel.start, Math.max(cuts.get(channel.start) ?? 0, widerBy(channel)))
  }
  return cuts
}

const moved = (extent: Extent, x: Spread, y: Spread): Extent => {
  const left = x(extent.left)
  const top = y(extent.top)
  return { left, top, right: left + (extent.right - extent.left), bottom: top + (extent.bottom - extent.top) }
}

const stretched = (extent: Extent, x: Spread, y: Spread): Extent => ({
  left: x(extent.left),
  top: y(extent.top),
  right: x(extent.right),
  bottom: y(extent.bottom),
})

const spread = (scene: RoutingScene, narrow: readonly Channel[]): RoutingScene => {
  const x = spreadOf(cutsOf(narrow, 'x'))
  const y = spreadOf(cutsOf(narrow, 'y'))
  return {
    elements: new Map([...scene.elements].map(([key, extent]) => [key, moved(extent, x, y)])),
    boxes: new Map([...scene.boxes].map(([key, extent]) => [key, stretched(extent, x, y)])),
    text: new Map([...scene.text].map(([key, extent]) => [key, stretched(extent, x, y)])),
    fixedLines: scene.fixedLines.map((line) => line.map((point) => ({ x: x(point.x), y: y(point.y) }))),
  }
}

/** The channels of *scene* too narrow for the lines its connectors are routed along. */
export const narrowChannels = (scene: RoutingScene, connectors: readonly Connector[]): Channel[] => {
  const result = routeAll(scene, connectors)
  const courses = [...[...result.routes.values()].map((routed) => routed.course), ...scene.fixedLines]
  const decorated = new Map(connectors.map((connector) => [connector.key, connector.decorated]))
  const ends = [...result.routes].flatMap(([key, routed]): (readonly [Point, number])[] => {
    const [source, target] = decorated.get(key) as readonly [boolean, boolean]
    return [
      [routed.course[0], runFor(source)],
      [routed.course[routed.course.length - 1], runFor(target)],
    ]
  })
  return tooNarrow(scene.boxes, [...scene.elements.values(), ...scene.text.values()], courses, scene.elements, ends)
}

/** *scene* with every channel too narrow for its lines opened until they fit, or ROUNDS tried. */
export const widened = (scene: RoutingScene, connectors: readonly Connector[]): RoutingScene => {
  let current = scene
  for (let round = 0; round < ROUNDS; round += 1) {
    const narrow = narrowChannels(current, connectors)
    if (narrow.length === 0) break
    current = spread(current, narrow)
  }
  return current
}
