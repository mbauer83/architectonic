/**
 * What part of the picture the canvas shows: PlantUML's page, grown to take in whatever is drawn beyond
 * it and never shrunk, so the picture keeps its scale while it is arranged. Held still while something
 * is dragged, so the point under the pointer keeps meaning the same place on the picture.
 */
import { computed, ref, watch, type Ref } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { extentAround, heightOf, unionOf, widthOf } from '../../../domain/layout/geometry'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import { useElementSize } from '../../composables/useElementSize'

/** Room round the drawing, so a shape dragged out of it stays in reach. */
const MARGIN = 40

export function useCanvasView(
  session: ArrangementSession, svg: Ref<SVGSVGElement | null>, dragging: Ref<boolean>,
  /** Further parts drawn round the picture — its title, its legend — which the view takes in too. */
  around: () => readonly Extent[] = () => [],
) {
  const geometry = computed(() => session.geometry.value)

  /** What is drawn now, shapes and lines: the view fits it, not PlantUML's page as such. */
  const drawnExtent = computed((): Extent | null => {
    const where = session.placement.value
    if (!where) return null
    const lines = extentAround([...session.courses.value.values()].flat())
    const all = [...where.elements.values(), ...where.boxes.values(), ...(lines ? [lines] : []), ...around()]
    if (all.length === 0) return null
    const drawn = unionOf(all)
    return {
      left: drawn.left - MARGIN, top: drawn.top - MARGIN, right: drawn.right + MARGIN, bottom: drawn.bottom + MARGIN,
    }
  })

  const view = ref<Extent | null>(null)
  const grown = (now: Extent | null): Extent | null => {
    const page = geometry.value?.canvas ?? null
    const before = view.value ?? page
    return now && before ? unionOf([before, now]) : (now ?? before)
  }
  watch(geometry, () => { view.value = null })
  watch(drawnExtent, (now) => {
    if (!dragging.value || !view.value) view.value = grown(now)
  }, { immediate: true })
  watch(dragging, (now) => { if (!now) view.value = grown(drawnExtent.value) })

  const viewBox = computed(() => {
    const extent = view.value
    return extent ? `${extent.left} ${extent.top} ${widthOf(extent)} ${heightOf(extent)}` : '0 0 100 100'
  })

  /** How wide the picture is shown on screen, in pixels: what a handle's size on screen is reckoned from. */
  const { width: shownWidth } = useElementSize(() => svg.value)

  /** One pixel on screen, in the picture's units: what the canvas's own marks are sized by. */
  const pixel = computed((): number => {
    const extent = view.value
    return extent && shownWidth.value > 0 ? widthOf(extent) / shownWidth.value : 1
  })

  const aspect = computed(() => {
    const extent = view.value
    return extent ? `${widthOf(extent)} / ${heightOf(extent)}` : '1 / 1'
  })

  /** PlantUML's background, stretched from the page it drew over the view the canvas shows. */
  const backdropTransform = computed((): string => {
    const drawn = geometry.value
    const extent = view.value
    if (!drawn || !extent) return ''
    const { canvas } = drawn
    const across = widthOf(extent) / widthOf(canvas)
    const down = heightOf(extent) / heightOf(canvas)
    return `translate(${extent.left} ${extent.top}) scale(${across} ${down}) translate(${-canvas.left} ${-canvas.top})`
  })

  return { view, viewBox, pixel, aspect, backdropTransform }
}
