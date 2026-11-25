/**
 * The arrows move a diagram window by a fifth of itself (02·9), where they have nothing else to do: on a
 * viewer whose elements are not walked by the keyboard — a viewpoint's view, an assurance projection.
 * Shift moves by a whole window. Not in a text field, and not with a modifier but Shift.
 */
import { onBeforeUnmount, watch, type Ref } from 'vue'
import { isTypingIn } from '../lib/keyboardScheme'

const ARROWS: Readonly<Record<string, readonly [number, number]>> = {
  ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
}
/** How far one press moves the window, as a share of its own size; with Shift, a whole window. */
const STEP = 0.2

export function useArrowPanning(
  host: Readonly<Ref<HTMLElement | null>>, panBy: (across: number, down: number) => void,
) {
  const onKeydown = (event: KeyboardEvent) => {
    const way = ARROWS[event.key]
    if (!way || isTypingIn(event.target) || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) {
      return
    }
    event.preventDefault()
    const step = event.shiftKey ? 1 : STEP
    panBy(way[0] * step, way[1] * step)
  }
  watch(host, (element, previous) => {
    previous?.removeEventListener('keydown', onKeydown)
    element?.addEventListener('keydown', onKeydown)
  }, { immediate: true })
  onBeforeUnmount(() => host.value?.removeEventListener('keydown', onKeydown))
}
