/** Remove two bends when the first and fourth legs can meet without crossing an obstacle. */
import type { Point } from '../geometry'
import { distanceBetween } from '../geometry'
import { Lines } from './lines'
import type { Connector } from './scene'
import { IDEAL_SEPARATION, runFor } from './scene'
import type { Passage, Visibility } from './visibility'

const clearLeg = (
  start: Point, old: Point, corner: Point, passage: Passage, minimum: number, occupied: Lines, arriving: boolean,
): boolean => {
  const dx = old.x - start.x
  const dy = old.y - start.y
  const distance = distanceBetween(start, corner)
  if (dx * (corner.x - start.x) + dy * (corner.y - start.y) <= 0 || distance < minimum) return false
  if (distance <= distanceBetween(start, old)) return true
  const [a, b] = arriving ? [corner, old] : [old, corner]
  return !passage.stepBlocked(a, b) && occupied.near(a, b, IDEAL_SEPARATION * 1.5) === 0
}

export const shorten = (
  courses: Map<string, Point[]>, connectors: readonly Connector[], visibility: Visibility,
  unseparated: readonly (readonly [string, string])[],
): void => {
  const unresolved = new Set(unseparated.flat())
  const occupied = new Lines()
  for (const course of [...courses.values(), ...visibility.scene.fixedLines]) {
    course.slice(1).forEach((b, index) => occupied.add(course[index], b))
  }
  for (const connector of connectors) {
    const course = courses.get(connector.key)
    if (!course || course.length < 5 || unresolved.has(connector.key)) continue
    const passage = visibility.passage([connector.source, connector.target])
    let index = 0
    while (index + 4 < course.length) {
      const [a, b, , d, e] = course.slice(index, index + 5)
      const corner = a.y === b.y ? { x: e.x, y: a.y } : { x: a.x, y: e.y }
      const source = index === 0 ? runFor(connector.decorated[0]) : 1
      const target = index + 5 === course.length ? runFor(connector.decorated[1]) : 1
      if (clearLeg(a, b, corner, passage, source, occupied, false) &&
          clearLeg(e, d, corner, passage, target, occupied, true)) {
        course.splice(index + 1, 3, corner)
        occupied.add(a, corner)
        occupied.add(corner, e)
      } else index += 1
    }
  }
}
