import { computed, onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * Pan and zoom over an element the caller owns.
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
  let dragging = false
  let drag = { x: 0, y: 0, tx: 0, ty: 0 }

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

  const onWheel = (event: WheelEvent) => {
    event.preventDefault()
    if (!containerRef.value) return
    const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
    const nextScale = Math.min(8, Math.max(0.2, scale.value * factor))
    const ratio = nextScale / scale.value
    const rect = containerRef.value.getBoundingClientRect()
    translateX.value = (event.clientX - rect.left) * (1 - ratio) + translateX.value * ratio
    translateY.value = (event.clientY - rect.top) * (1 - ratio) + translateY.value * ratio
    scale.value = nextScale
  }

  const onMouseMove = (event: MouseEvent) => {
    if (!dragging) return
    translateX.value = drag.tx + event.clientX - drag.x
    translateY.value = drag.ty + event.clientY - drag.y
  }

  const onMouseUp = () => {
    dragging = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  const startDrag = (event: MouseEvent) => {
    event.preventDefault()
    dragging = true
    drag = { x: event.clientX, y: event.clientY, tx: translateX.value, ty: translateY.value }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  watch(containerRef, (element, previous) => {
    previous?.removeEventListener('wheel', onWheel)
    element?.addEventListener('wheel', onWheel, { passive: false })
  })
  if (resetSignal) watch(resetSignal, resetView)
  onUnmounted(() => {
    containerRef.value?.removeEventListener('wheel', onWheel)
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  })

  return { canvasStyle, isTransformed, resetView, startDrag }
}
