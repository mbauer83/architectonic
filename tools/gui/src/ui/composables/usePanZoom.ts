import { computed, ref, watch, type Ref } from 'vue'
import { usePanGesture } from './usePanGesture'
import { useWheelZoom } from './useWheelZoom'

/**
 * Pan and zoom over an element the caller owns, framed by a fixed reset to scale 1 at the origin.
 *
 * The gestures themselves are `usePanGesture` and `useWheelZoom`, shared with `useFittedPanZoom`;
 * what this composable adds is the framing, and a `resetSignal` its callers can pull to restore it.
 *
 * The element is passed in rather than returned: a composable that created the ref would also be
 * dictating the `ref="…"` name its callers must write in their template, a coupling nothing checks.
 */
export const usePanZoom = (
  containerRef: Readonly<Ref<HTMLElement | null>>,
  resetSignal?: Ref<unknown>,
) => {
  const scale = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)
  const { onMouseDown } = usePanGesture(translateX, translateY)
  useWheelZoom(containerRef, { scale, tx: translateX, ty: translateY })

  const canvasStyle = computed(() => ({
    transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
    transformOrigin: '0 0',
    willChange: 'transform',
    display: 'inline-block',
  }))
  const isTransformed = computed(() => scale.value !== 1 || translateX.value !== 0 || translateY.value !== 0)

  const resetView = () => {
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
  }

  if (resetSignal) watch(resetSignal, resetView)

  return { canvasStyle, isTransformed, resetView, onMouseDown }
}
