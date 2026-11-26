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
 * How long one screen pixel is on the picture *svg* draws, however it is zoomed — by its view box and by
 * the window round it: what a tolerance stated in screen pixels is measured in. One where it is not drawn.
 */
export const pictureUnitsPerScreenPixel = (svg: SVGSVGElement | null): number => {
  const matrix = svg?.getScreenCTM()
  const across = matrix ? Math.hypot(matrix.a, matrix.b) : 0
  return across > 0 ? 1 / across : 1
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
