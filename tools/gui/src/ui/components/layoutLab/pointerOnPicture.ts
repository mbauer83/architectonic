/**
 * The canvas's pointer, shared by its gestures: where a pointer event falls on the picture, and a drag
 * followed on the window to its release.
 */
import type { Point } from '../../../domain/layout/geometry'

/** Where *event* falls on the picture *svg* draws, in the picture's own units. */
export const pointOnPicture = (svg: SVGSVGElement | null, event: { clientX: number; clientY: number }): Point => {
  const matrix = svg?.getScreenCTM()
  if (!matrix) return { x: event.clientX, y: event.clientY }
  const inverse = matrix.inverse()
  return {
    x: inverse.a * event.clientX + inverse.c * event.clientY + inverse.e,
    y: inverse.b * event.clientX + inverse.d * event.clientY + inverse.f,
  }
}

/**
 * Follow a drag on the window, not by pointer capture: pressing a piece paints it in front, which moves
 * its node, and a moved node loses its capture — the release then landed nowhere. Answers the switch.
 */
export const followingPointer = (
  moved: (event: PointerEvent) => void, released: (event: PointerEvent) => void,
): ((on: boolean) => void) => (on) => {
  const followed = [['pointermove', moved], ['pointerup', released], ['pointercancel', released]] as const
  for (const [type, listener] of followed) {
    if (on) window.addEventListener(type, listener)
    else window.removeEventListener(type, listener)
  }
}
