/**
 * The one popover in-canvas editing opens at a point (sketch 03): which level of it is open, where, and
 * how it closes. It stays inside the viewport, moved left and up by what it would overhang; focus stays
 * in it from one level to the next, so Escape closes it rather than leaving edit mode; a press outside
 * closes it, and Escape gives focus back to the canvas.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

export type CanvasPopoverLevel =
  'create' | 'element' | 'selection' | 'line' | 'rename' | 'delete' | 'target' | 'relation' | 'nest' | 'box' | 'label'

/** How wide a level's surface is: the picker wide, a confirmation wider still, a form between, a menu its own. */
const WIDTH: Partial<Record<CanvasPopoverLevel, string>> = {
  create: 'canvas-pop--wide', delete: 'canvas-pop--dialog', rename: 'canvas-pop--form', relation: 'canvas-pop--form',
  nest: 'canvas-pop--form', label: 'canvas-pop--form',
}

export function useCanvasPopover(host: Ref<HTMLElement | null>, pop: Ref<HTMLElement | null>) {
  const mode = ref<CanvasPopoverLevel | null>(null)
  const at = ref({ x: 0, y: 0 })
  const error = ref('')
  const width = computed(() => (mode.value && WIDTH[mode.value]) ?? '')

  const position = (x: number, y: number) => {
    at.value = { x, y }
    error.value = ''
  }
  const fit = () => {
    const box = pop.value?.getBoundingClientRect()
    if (!box) return
    const x = Math.max(8, Math.min(at.value.x, window.innerWidth - box.width - 8))
    const y = Math.max(8, Math.min(at.value.y, window.innerHeight - box.height - 8))
    if (x !== at.value.x || y !== at.value.y) at.value = { x, y }
  }
  watch([mode, at], () => void nextTick(fit), { flush: 'post' })
  // A level grows within itself — the picker opening into the create form — and is fitted again as it
  // does, or what it grew by lands below the window, out of reach.
  const grown = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => fit())
  watch(pop, (now, before) => {
    if (before) grown?.unobserve(before)
    if (now) grown?.observe(now)
  })
  onBeforeUnmount(() => grown?.disconnect())
  // On what the level marks to start on, or on the popover itself when its content took no focus.
  watch(mode, () => void nextTick(() => nextTick(() => {
    if (!pop.value || pop.value.contains(document.activeElement)) return
    ;(pop.value.querySelector<HTMLElement>('[data-autofocus]') ?? pop.value).focus()
  })), { flush: 'post' })

  const close = (refocus = false) => {
    mode.value = null
    if (refocus) host.value?.focus({ preventScroll: true })
  }
  const outside = (event: PointerEvent) => {
    if (mode.value && !pop.value?.contains(event.target as Node)) close()
  }
  window.addEventListener('pointerdown', outside, true)
  onBeforeUnmount(() => window.removeEventListener('pointerdown', outside, true))

  return { mode, at, error, width, position, close }
}
