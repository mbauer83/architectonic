import { watch, type Ref } from 'vue'
import type { Extent } from '../../domain/layout/geometry'

/** One element as the keyboard reaches it: where it is drawn and how it is announced. */
interface Stop {
  readonly id: string
  readonly element: SVGGraphicsElement
  readonly box: Extent
}

const boxOf = (element: SVGGraphicsElement): Extent | null => {
  try {
    const box = element.getBBox()
    return { left: box.x, top: box.y, right: box.x + box.width, bottom: box.y + box.height }
  } catch { return null }
}

/** Top to bottom, then left to right; shapes whose tops are within a few units share a row. */
const ROW = 8
const readingOrder = (one: Stop, other: Stop): number =>
  Math.abs(one.box.top - other.box.top) > ROW ? one.box.top - other.box.top : one.box.left - other.box.left

const centre = (box: Extent) => ({ x: (box.left + box.right) / 2, y: (box.top + box.bottom) / 2 })

const DIRECTIONS: Readonly<Record<string, { x: number; y: number }>> = {
  ArrowRight: { x: 1, y: 0 }, ArrowLeft: { x: -1, y: 0 }, ArrowDown: { x: 0, y: 1 }, ArrowUp: { x: 0, y: -1 },
}

/** The nearest stop from *from* in a direction: ahead of it, weighing sideways distance double. */
const nearest = (from: Stop, stops: readonly Stop[], direction: { x: number; y: number }): Stop | null => {
  const here = centre(from.box)
  let best: Stop | null = null
  let bestScore = Number.POSITIVE_INFINITY
  for (const stop of stops) {
    if (stop === from) continue
    const there = centre(stop.box)
    const ahead = (there.x - here.x) * direction.x + (there.y - here.y) * direction.y
    if (ahead <= 0) continue
    const aside = Math.abs((there.x - here.x) * direction.y + (there.y - here.y) * direction.x)
    const score = ahead + 2 * aside
    if (score < bestScore) { best = stop; bestScore = score }
  }
  return best
}

/**
 * Reading a diagram without a pointer (B97). The canvas is one `Tab` stop; `Enter` or an arrow goes in
 * to the elements, and the arrows then move to the nearest element that way. `Enter` selects the
 * focused element and the reading starts; `Shift`+`Enter` adds it or takes it away. `F` frames the
 * reading. `Esc` clears the selection, and pressed again leaves the elements. `Tab` goes on to the panel.
 *
 * Each element is focusable in reading order and announced by name, type and position, and the window
 * follows the focus. Focus and selection are different states and are drawn differently.
 */
export function useReadingKeyboard(options: {
  host: Ref<HTMLElement | null>
  nodeElements: Ref<ReadonlyMap<string, readonly Element[]>>
  describe: (id: string) => { name: string; type: string } | null
  selectedIds: Ref<readonly string[]>
  select: (id: string, additive: boolean) => void
  clear: () => void
  frame: () => void
  reveal: (box: Extent) => void
  enabled: Ref<boolean>
}) {
  let stops: Stop[] = []

  watch(options.nodeElements, (nodes) => {
    stops = [...nodes].flatMap(([id, elements]) => {
      const element = elements.find((one): one is SVGGraphicsElement => one instanceof SVGGraphicsElement)
      const box = element ? boxOf(element) : null
      return element && box ? [{ id, element, box }] : []
    }).sort(readingOrder)
    stops.forEach((stop, index) => {
      const about = options.describe(stop.id)
      stop.element.setAttribute('tabindex', '-1')
      stop.element.setAttribute('role', 'button')
      stop.element.setAttribute('data-reading-stop', '')
      stop.element.setAttribute('aria-label',
        `${about?.name ?? stop.id}, ${about?.type ?? 'element'}, ${index + 1} of ${stops.length}`)
    })
  }, { flush: 'post' })

  const focused = (): Stop | null => {
    const active = document.activeElement
    return stops.find((stop) => stop.element === active) ?? null
  }

  const focusStop = (stop: Stop | undefined | null) => {
    if (!stop) return
    stop.element.focus({ preventScroll: true })
    options.reveal(stop.box)
  }

  const onKeydown = (event: KeyboardEvent) => {
    if (!options.enabled.value || event.ctrlKey || event.metaKey || event.altKey) return
    const at = focused()
    const direction = DIRECTIONS[event.key]
    if (direction) {
      event.preventDefault()
      focusStop(at ? nearest(at, stops, direction) : stops[0])
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (at) options.select(at.id, event.shiftKey)
      else focusStop(stops[0])
    } else if (event.key === 'Escape') {
      if (options.selectedIds.value.length > 0) options.clear()
      else if (at) options.host.value?.focus({ preventScroll: true })
      else return
      event.preventDefault()
    } else if ((event.key === 'f' || event.key === 'F') && options.selectedIds.value.length > 0) {
      event.preventDefault()
      options.frame()
    }
  }

  return { onKeydown }
}
