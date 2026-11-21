/**
 * The router, held to the routes the Python router answers for the same scenes.
 *
 * `tests/fixtures/layout_geometry/routing.json` holds scenes, their connectors and what
 * `src/domain/diagrams/layout/routing` answers: every route's ports and course, the unroutable
 * connectors, the pairs nudging could not separate — and, under `graph`, the visibility graph one
 * scene builds: its segments and every join once a search's terminals are joined to it. pytest holds
 * the file to the Python router; this holds the TypeScript one to the file, to the pixel.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../geometry'
import type { Port } from '../../orthogonal'
import { EAST, SOUTH } from '../graph'
import { routeAll } from '../router'
import type { Connector, RoutedConnector, RoutingResult, RoutingScene } from '../scene'
import { Visibility } from '../visibility'

type XY = readonly [number, number]

interface SceneJson {
  elements: Record<string, Extent>
  boxes: Record<string, Extent>
  text: Record<string, Extent>
  fixed_lines: XY[][]
}

interface ConnectorJson {
  key: string
  source: string
  target: string
  decorated: [boolean, boolean]
  source_port?: Port
  target_port?: Port
}

interface RoutedJson {
  source_port: Port
  target_port: Port
  course: XY[]
}

interface ResultJson {
  routes: Record<string, RoutedJson>
  unroutable: string[]
  unseparated: [string, string][]
}

const routing = JSON.parse(
  readFileSync(fileURLToPath(new URL('../../../../../../../tests/fixtures/layout_geometry/routing.json', import.meta.url)), 'utf-8'),
) as {
  graph: {
    scene: SceneJson
    terminals: XY[]
    level: (number | null)[][]
    upright: (number | null)[][]
    joins: number[][]
  }
  cases: { name: string; scene: SceneJson; connectors: ConnectorJson[]; result: ResultJson }[]
  quick: { scene: SceneJson; connectors: ConnectorJson[]; previous: Record<string, RoutedJson>; changed: string[]; result: ResultJson }
}

const sceneOf = (json: SceneJson): RoutingScene => ({
  elements: new Map(Object.entries(json.elements)),
  boxes: new Map(Object.entries(json.boxes)),
  text: new Map(Object.entries(json.text)),
  fixedLines: json.fixed_lines.map((line) => line.map(([x, y]) => ({ x, y }))),
})

const connectorOf = (json: ConnectorJson): Connector => ({
  key: json.key,
  source: json.source,
  target: json.target,
  decorated: json.decorated,
  ...(json.source_port ? { sourcePort: json.source_port } : {}),
  ...(json.target_port ? { targetPort: json.target_port } : {}),
})

const routedOf = (key: string, json: RoutedJson): RoutedConnector => ({
  key,
  sourcePort: json.source_port,
  targetPort: json.target_port,
  course: json.course.map(([x, y]) => ({ x, y })),
})

const asJson = (result: RoutingResult): ResultJson => ({
  routes: Object.fromEntries(
    [...result.routes].map(([key, routed]) => [
      key,
      {
        source_port: routed.sourcePort,
        target_port: routed.targetPort,
        course: routed.course.map((point): XY => [point.x, point.y]),
      },
    ]),
  ),
  unroutable: [...result.unroutable],
  unseparated: result.unseparated.map(([first, second]): [string, string] => [first, second]),
})

/** A segment's end as the file writes it: null where nothing stops it. */
const end = (value: number): number | null => (Number.isFinite(value) ? value : null)

const byJoin = (one: number[], other: number[]): number =>
  one[0] - other[0] || one[1] - other[1] || one[2] - other[2] || one[3] - other[3]

describe('the visibility graph is the one the Python router builds', () => {
  const { scene, terminals, level, upright, joins } = routing.graph
  const graph = new Visibility(sceneOf(scene)).graph

  it('stops each segment where the Python one stops', () => {
    expect(graph.level.segments.map(([at, low, high]) => [at, end(low), end(high)])).toEqual(level)
    expect(graph.upright.segments.map(([at, low, high]) => [at, end(low), end(high)])).toEqual(upright)
  })

  it('joins a search\'s terminals to the same nodes', () => {
    const joined = graph.joined(terminals.map(([x, y]) => ({ x, y })))
    const answered: number[][] = []
    for (let node = 0; node < joined.size; node += 1) {
      for (const direction of [EAST, SOUTH]) {
        const other = joined.next(node, direction)
        if (other >= 0) answered.push([joined.x(node), joined.y(node), joined.x(other), joined.y(other)])
      }
    }
    expect(answered.sort(byJoin)).toEqual(joins)
  })
})

describe('the router answers what the Python router answers', () => {
  it('holds enough cases to mean something', () => {
    expect(routing.cases.length).toBeGreaterThanOrEqual(10)
  })

  it.each(routing.cases)('$name', ({ scene, connectors, result }) => {
    expect(asJson(routeAll(sceneOf(scene), connectors.map(connectorOf)))).toEqual(result)
  })

  it("a drag's quick pass routes only what moved", () => {
    const { scene, connectors, previous, changed, result } = routing.quick
    const answered = routeAll(sceneOf(scene), connectors.map(connectorOf), {
      previous: new Map(Object.entries(previous).map(([key, json]) => [key, routedOf(key, json)])),
      changed: new Set(changed),
    })
    expect(asJson(answered)).toEqual(result)
  })
})
