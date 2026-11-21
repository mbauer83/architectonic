/**
 * What a router is given and what it answers: the scene, the connectors, the routes.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/scene.py`. Orthogonal connector
 * routing after Wybrow, Marriott and Stuckey (GD 2009): a visibility graph over the obstacles, A*
 * per connector costing length and bends, then nudging. The two implementations are held equal by
 * `tests/fixtures/layout_geometry/routing.json`.
 */
import type { Extent, Point } from '../geometry'
import type { Port, Side } from '../orthogonal'
import { STUB } from '../orthogonal'
import { END_RUN, LINE_CLEARANCE } from '../routeQuality'

/** How far a route keeps from an element it does not end at. */
export const BUFFER = 8

/** What one bend costs, in pixels of length a route would rather run than turn. */
export const BEND_PENALTY = 50

/** How much more a pixel of run costs for each route already running alongside it. */
export const CROWDING = 2

/** How far either side of a box's border a candidate line runs. */
export const BORDER_OFFSET = LINE_CLEARANCE + 4

/** How far apart nudging places runs that share a line, where there is room. */
export const IDEAL_SEPARATION = 12

/** How long the straight run out of a port is: a decoration and a clear run, else a stub. */
export const runFor = (decorated: boolean): number => (decorated ? END_RUN : STUB)

export interface Connector {
  readonly key: string
  readonly source: string
  readonly target: string
  readonly decorated: readonly [boolean, boolean]
  readonly sourcePort?: Port
  readonly targetPort?: Port
}

export interface RoutingScene {
  readonly elements: ReadonlyMap<string, Extent>
  readonly boxes: ReadonlyMap<string, Extent>
  readonly text: ReadonlyMap<string, Extent>
  readonly fixedLines: readonly (readonly Point[])[]
}

export const extentOf = (scene: RoutingScene, key: string): Extent => {
  const extent = scene.elements.get(key) ?? scene.boxes.get(key)
  if (!extent) throw new Error(`the scene holds nothing called ${key}`)
  return extent
}

export interface RoutedConnector {
  readonly key: string
  readonly sourcePort: Port
  readonly targetPort: Port
  readonly course: readonly Point[]
}

export interface RoutingResult {
  readonly routes: ReadonlyMap<string, RoutedConnector>
  readonly unroutable: readonly string[]
  readonly unseparated: readonly (readonly [string, string])[]
}

export const SIDES: readonly Side[] = ['top', 'right', 'bottom', 'left']

export const sameExtent = (one: Extent, other: Extent): boolean =>
  one.left === other.left && one.top === other.top && one.right === other.right && one.bottom === other.bottom

/** Python's ordering of strings, which both sides sort keys by. */
export const byText = (one: string, other: string): number => (one < other ? -1 : one > other ? 1 : 0)
