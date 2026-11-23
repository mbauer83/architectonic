import { onBeforeUnmount, ref, type Ref } from 'vue'
import type { DiagramEditing } from './useDiagramEditing'

export const elementAt = (event: Event) =>
  event.target instanceof Element ? event.target.closest<SVGGElement>('[data-alias]') : null

export function useContentGestures(
  host: Ref<HTMLElement | null>, editing: DiagramEditing, source: Ref<string>,
  position: (x: number, y: number) => void, rename: (alias: string) => void,
  editLine: (index: number) => void, pair: (alias: string) => void,
) {
  const touchedLine = ref<number | null>(null)
  let hold: ReturnType<typeof setTimeout> | undefined
  let down: { alias: string; x: number; y: number; edge: boolean } | null = null
  function release() {
    clearTimeout(hold)
    down = null
  }
  onBeforeUnmount(release)
  function press(e: PointerEvent) {
    if (e.button !== 0) return
    const line = (e.target as Element).closest<SVGElement>('[data-relation]')
    const svg = host.value?.querySelector('svg')
    const matrix = svg?.getScreenCTM()
    const endpoint =
      matrix &&
      [...editing.session.courses.value].find(([, points]) => {
        return [points[0], points.at(-1)].some((point) => {
          if (!point) return false
          const screen = new DOMPoint(point.x, point.y).matrixTransform(matrix)
          return Math.hypot(screen.x - e.clientX, screen.y - e.clientY) <= 5
        })
      })
    if (line || endpoint) {
      e.stopPropagation()
      touchedLine.value = endpoint?.[0] ?? Number(line?.dataset.relation)
      position(e.clientX, e.clientY)
      const index = touchedLine.value
      hold = setTimeout(() => editLine(index), 550)
      return
    }
    touchedLine.value = null
    const el = elementAt(e)
    if (!el) return
    const alias = el.dataset.alias ?? ''
    const rect = el.getBoundingClientRect()
    const edge =
      Math.min(
        Math.abs(e.clientX - rect.left),
        Math.abs(e.clientX - rect.right),
        Math.abs(e.clientY - rect.top),
        Math.abs(e.clientY - rect.bottom),
      ) < 5
    if (edge) e.stopPropagation()
    down = { alias, x: e.clientX, y: e.clientY, edge }
    hold = setTimeout(() => {
      position(rect.left, rect.top)
      void rename(alias)
      release()
    }, 550)
  }
  function moving(e: PointerEvent) {
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) clearTimeout(hold)
  }
  function up(e: PointerEvent) {
    if (down?.edge) {
      const dest = document.elementFromPoint(e.clientX, e.clientY)?.closest<SVGElement>('[data-alias]')
        ?.dataset.alias
      if (dest && dest !== down.alias) {
        source.value = down.alias
        position(e.clientX, e.clientY)
        void pair(dest)
      }
    }
    release()
  }
  function focusCanvas(e: PointerEvent) {
    if (e.button === 0) host.value?.focus({ preventScroll: true })
    press(e)
  }
  return { touchedLine, focusCanvas, up, release, moving }
}
