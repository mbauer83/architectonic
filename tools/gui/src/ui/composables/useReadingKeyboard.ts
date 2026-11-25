import { watch, type Ref } from 'vue'
import type { Extent } from '../../domain/layout/geometry'
import { ARROW_DIRECTIONS, inReadingOrder, nearestTowards } from '../../domain/layout/keyboardReach'
import { pictureExtentOf } from '../lib/svgExtent'

/** One element as the keyboard reaches it: where it is drawn, its drawing, and how it is announced. */
interface Stop {
  readonly id: string
  readonly element: SVGGraphicsElement
  readonly box: Extent
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
  /** How an element is announced: its name and type, and whether it is a draft (03·4). */
  describe: (id: string) => { name: string; type: string; draft?: boolean } | null
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
      const box = element ? pictureExtentOf(element) : null
      return element && box ? [{ id, element, box }] : []
    }).sort((one, other) => inReadingOrder(one.box, other.box))
    stops.forEach((stop, index) => {
      const about = options.describe(stop.id)
      stop.element.setAttribute('tabindex', '-1')
      stop.element.setAttribute('role', 'button')
      stop.element.setAttribute('data-reading-stop', '')
      stop.element.setAttribute('aria-label',
        `${about?.name ?? stop.id}, ${about?.type ?? 'element'}${about?.draft ? ', draft' : ''}, `
        + `${index + 1} of ${stops.length}`)
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
    const direction = ARROW_DIRECTIONS[event.key]
    if (direction) {
      event.preventDefault()
      focusStop(at ? nearestTowards(at.box, stops.filter((stop) => stop !== at), direction) : stops[0])
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
