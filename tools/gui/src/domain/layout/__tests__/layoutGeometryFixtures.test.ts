/**
 * The layout geometry rules, held to the cases the Python domain is held to.
 *
 * `tests/fixtures/layout_geometry/*.json` states each rule as cases with their answers. pytest holds
 * those files to what `src/domain/diagrams/layout` computes; this file holds
 * `tools/gui/src/domain/layout` to the same files. Neither side can move alone, which is the only
 * thing that keeps a route the canvas shows while dragging equal to the one the server stores.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Breach } from '../attachment'
import {
  breachesOf,
  elementsCrossed,
  endsConflict,
  keepAttached,
  reattached,
} from '../attachment'
import type { Extent, Point } from '../geometry'
import { heightOf, widthOf } from '../geometry'
import type { Route } from '../orthogonal'
import { courseOf, fractionAlong, pointAlong, statedCourse } from '../orthogonal'

const FIXTURES = new URL('../../../../../../tests/fixtures/layout_geometry/', import.meta.url)

const fixture = <Content>(name: string): Content =>
  JSON.parse(readFileSync(fileURLToPath(new URL(name, FIXTURES)), 'utf-8')) as Content

type XY = readonly [number, number]

interface EndsCase {
  readonly name: string
  readonly source: Extent | null
  readonly target: Extent | null
  readonly route: Route
}

const asPairs = (course: readonly Point[]): XY[] => course.map((point) => [point.x, point.y])

/** A route as the fixtures write one: no `via` where there are no bends. */
const asWritten = (route: Route): Route => {
  const { via, ...rest } = route
  return via?.length ? { ...rest, via } : rest
}

describe('the course a stated route runs', () => {
  const { courses, along } = fixture<{
    courses: (EndsCase & { course: XY[] })[]
    along: {
      course: XY[]
      points: { at: number; point: XY }[]
      fractions: { point: XY; fraction: number }[]
    }
  }>('courses.json')

  it.each(courses)('$name', ({ source, target, route, course }) => {
    expect(asPairs(statedCourse(route, source, target))).toEqual(course)
  })

  it('states enough cases to mean something', () => {
    expect(courses.length).toBeGreaterThanOrEqual(12)
  })

  const walked = along.course.map(([x, y]) => ({ x, y }))

  it.each(along.points)('the point $at of the way along', ({ at, point }) => {
    const found = pointAlong(walked, at)
    expect(found.x).toBeCloseTo(point[0], 9)
    expect(found.y).toBeCloseTo(point[1], 9)
  })

  it.each(along.fractions)('how far along the place nearest $point lies', ({ point, fraction }) => {
    expect(fractionAlong(walked, { x: point[0], y: point[1] })).toBeCloseTo(fraction, 9)
  })
})

describe('what a route fails to keep towards its ends', () => {
  const { breaches, crossed, conflicts } = fixture<{
    breaches: (EndsCase & { breaches: Breach[] })[]
    crossed: {
      name: string
      extents: Record<string, Extent>
      ends: [string, string]
      route: Route
      crossed: string[]
    }[]
    conflicts: { name: string; source: Extent; target: Extent; conflict: boolean }[]
  }>('breaches.json')

  it.each(breaches)('$name', ({ source, target, route, breaches: expected }) => {
    expect(breachesOf(route, source, target)).toEqual(expected)
  })

  it.each(crossed)('I5: $name', ({ extents, ends, route, crossed: expected }) => {
    const course = courseOf(route, extents[ends[0]], extents[ends[1]])
    expect(course).not.toBeNull()
    expect(elementsCrossed(course ?? [], new Map(Object.entries(extents)), ends)).toEqual(expected)
  })

  it.each(conflicts)('two connected elements $name', ({ source, target, conflict }) => {
    expect(endsConflict(source, target)).toBe(conflict)
  })
})

describe('keeping one route attached', () => {
  const { repairs } = fixture<{
    repairs: { name: string; route: Route; source: Extent; target: Extent; reattached: Route }[]
  }>('repairs.json')

  it.each(repairs)('$name', ({ route, source, target, reattached: expected }) => {
    expect(asWritten(reattached(route, source, target))).toEqual(expected)
  })
})

describe('four hundred random moves', () => {
  interface Step {
    readonly move: string
    readonly to: XY
    readonly routes: Record<string, Route>
    readonly crossing: Record<string, string[]>
    readonly conflicts: string[]
    readonly rerouted: Record<string, Route>
  }
  const walk = fixture<{
    extents: Record<string, Extent>
    ends: Record<string, [string, string]>
    routes: Record<string, Route>
    steps: Step[]
  }>('walk.json')

  it('leave every arrow as the server leaves it, and none detached', () => {
    const extents = new Map(Object.entries(walk.extents))
    const ends = new Map(Object.entries(walk.ends))
    let routes: ReadonlyMap<string, Route> = new Map(Object.entries(walk.routes))
    const failures: string[] = []

    expect(walk.steps.length).toBeGreaterThanOrEqual(400)
    walk.steps.forEach((step, index) => {
      const before = extents.get(step.move)
      if (!before) throw new Error(`step ${index} moves ${step.move}, which the walk does not hold`)
      const [left, top] = step.to
      extents.set(step.move, { left, top, right: left + widthOf(before), bottom: top + heightOf(before) })

      const kept = keepAttached(routes, { ends, extents, changed: [step.move] })
      const changed = Object.fromEntries(
        [...kept.routes]
          .filter(([key, route]) => route !== routes.get(key))
          .map(([key, route]) => [key, asWritten(route)]),
      )
      // A route repaired into exactly what it was is not a change the server records either.
      const recorded = Object.fromEntries(
        Object.entries(changed).filter(
          ([key, route]) => JSON.stringify(route) !== JSON.stringify(asWritten(routes.get(key) ?? {})),
        ),
      )
      expect(recorded, `step ${index}: routes`).toEqual(step.routes)
      expect(Object.fromEntries(kept.crossing), `step ${index}: crossing`).toEqual(step.crossing)
      expect(kept.conflicts, `step ${index}: conflicts`).toEqual(step.conflicts)

      // The canvas takes the server's route for an arrow that came to cross an element.
      routes = new Map([...kept.routes, ...Object.entries(step.rerouted)])
      for (const [key, route] of routes) {
        const [sourceKey, targetKey] = ends.get(key) ?? ['', '']
        const source = extents.get(sourceKey) ?? null
        const target = extents.get(targetKey) ?? null
        const broken = breachesOf(route, source, target)
        if (broken.length > 0 && source && target && !endsConflict(source, target)) {
          failures.push(`step ${index}: ${key} ${broken.join(' ')}`)
        }
      }
    })

    expect(failures).toEqual([])
  })
})
