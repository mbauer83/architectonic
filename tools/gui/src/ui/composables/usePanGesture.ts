import { onUnmounted, type Ref } from 'vue'

/**
 * Pointer travel, in screen pixels, before a press becomes a pan.
 *
 * The same figure `useGraphPanZoom` settled on for promoting a press to a node drag: it is a
 * property of the hand, not of what is being dragged, so the two should not disagree.
 */
const PAN_THRESHOLD_PX = 4

/**
 * Elements that own their press outright, so a drag starting on one is never a pan.
 *
 * Deliberately short. Anything that merely *responds* to a click — a diagram entity, a connection,
 * a drill-down badge — is not on it, because those are exactly what the ambiguity is about.
 */
const NON_PANNABLE = 'button, a, input, label, select, textarea'

/**
 * Press-and-drag panning over a viewport whose contents are also click-to-select.
 *
 * The two gestures share the primary button, so the only thing separating them is travel. A press
 * that stays put is a click and reaches whatever it landed on; a press that moves pans the
 * viewport, and the click that mouseup would otherwise produce is swallowed so the thing under the
 * pointer is not also selected.
 *
 * Both diagram viewports used to resolve the ambiguity the other way, by declining to pan at all
 * when the press landed on `[data-entity-id]` or `[data-conn-id]`. That made every model entity a
 * dead zone, and a diagram dense enough to need panning is one whose boxes cover most of the
 * viewport — so panning was unreachable exactly when it was wanted, and only the auto-created
 * grouping boxes, which carry no entity id, still dragged.
 *
 * `tx`/`ty` are the caller's own translation refs rather than state returned from here: both
 * callers already compute a transform from them, and the reset/fit paths write them directly.
 */
export function usePanGesture(tx: Ref<number>, ty: Ref<number>) {
  let pressed: { x: number; y: number; tx: number; ty: number } | null = null
  let panning = false

  const swallowClick = (event: MouseEvent) => {
    event.stopPropagation()
    event.preventDefault()
  }
  const disarmSwallow = () => window.removeEventListener('click', swallowClick, { capture: true })

  const onMouseMove = (event: MouseEvent) => {
    if (pressed === null) return
    const dx = event.clientX - pressed.x
    const dy = event.clientY - pressed.y
    if (!panning && Math.hypot(dx, dy) < PAN_THRESHOLD_PX) return
    panning = true
    // Anchored on where the press started rather than on where the threshold was crossed, so the
    // content tracks the pointer one-to-one instead of trailing it by the threshold distance.
    tx.value = pressed.tx + dx
    ty.value = pressed.ty + dy
  }

  const onMouseUp = () => {
    if (panning) {
      // Capture phase, so the click is stopped before the entity's own bubble-phase listener sees
      // it. `once` covers the ordinary case; the timeout covers a mouseup that no click follows,
      // which would otherwise leave this armed for the next, unrelated click. The click is
      // dispatched in the same task as the mouseup, so a macrotask hop is late enough to be sure.
      window.addEventListener('click', swallowClick, { capture: true, once: true })
      window.setTimeout(disarmSwallow, 0)
    }
    pressed = null
    panning = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  const onMouseDown = (event: MouseEvent) => {
    if (event.button !== 0) return
    if (event.target instanceof Element && event.target.closest(NON_PANNABLE)) return
    // Stops the press selecting whatever label text is under the pointer as the diagram moves.
    event.preventDefault()
    pressed = { x: event.clientX, y: event.clientY, tx: tx.value, ty: ty.value }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  onUnmounted(() => {
    pressed = null
    panning = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
    disarmSwallow()
  })

  return { onMouseDown }
}
