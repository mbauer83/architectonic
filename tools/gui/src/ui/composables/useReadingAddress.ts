import { nextTick, watch, type Ref } from 'vue'
import type { LocationQuery, RouteLocationNormalizedLoaded, Router } from 'vue-router'
import type { Reach, ReadingView } from '../../domain/diagramReading'
import { readingFromQuery, readingQuery, resolveFocus } from '../../domain/diagramReading'

/** The address's parameters a reading owns; every other parameter on the page is left as it is. */
const OWN = ['focus', 'reach', 'view']

const sameQuery = (one: LocationQuery, other: Record<string, string>): boolean => {
  const keys = new Set([...Object.keys(one), ...Object.keys(other)])
  return [...keys].every((key) => String(one[key] ?? '') === String(other[key] ?? ''))
}

/**
 * The reading in the page's address, so it can be linked (B97): `focus`, `reach` and `view`.
 *
 * A new selection, or a new reach, adds a history entry, so Back returns to the previous reading;
 * moving the window replaces the entry. The window is written only once the reader has moved it —
 * a diagram fitted as it opened needs no `view` — and the reading lens is never written.
 *
 * Read back whenever the address changes under the page (Back, Forward, a pasted link), once the
 * picture is mapped, so the stems in it can be resolved against what the diagram draws.
 */
export function useReadingAddress(options: {
  route: RouteLocationNormalizedLoaded
  router: Router
  /** Whether the reading is the page's to write: view mode, with the picture mapped. */
  ready: Ref<boolean>
  selectedIds: Ref<readonly string[]>
  drawnIds: () => readonly string[]
  reach: Ref<Reach>
  select: (ids: readonly string[]) => void
  window: {
    moved: Ref<boolean>
    current: () => ReadingView | null
    show: (view: ReadingView) => void
    /** Back to the window the diagram opened at. */
    reset: () => void
    /** What moving the window changes, watched to replace the history entry. */
    changes: () => unknown
  }
}) {
  const { route, router, ready, selectedIds, reach } = options

  const wanted = (): Record<string, string> => {
    const kept = Object.fromEntries(Object.entries(route.query).filter(([key]) => !OWN.includes(key))) as
      Record<string, string>
    const view = options.window.moved.value ? options.window.current() : null
    return { ...kept, ...readingQuery({ focus: selectedIds.value, reach: reach.value, view }) }
  }

  // While an address is being read back, what that changes is not a new reading to write: written, it
  // would push an entry on top of the one Back just returned to.
  let applying = false

  const write = (how: 'push' | 'replace') => {
    if (!ready.value || applying) return
    const query = wanted()
    if (sameQuery(route.query, query)) return
    void router[how]({ query })
  }

  const read = () => {
    if (!ready.value) return
    applying = true
    void nextTick().then(() => { applying = false })
    const addressed = readingFromQuery(route.query)
    if (addressed.reach.incoming !== reach.value.incoming || addressed.reach.outgoing !== reach.value.outgoing) {
      reach.value = addressed.reach
    }
    const focus = resolveFocus(addressed.focus, options.drawnIds())
    if (focus.join(',') !== selectedIds.value.join(',')) options.select(focus)
    if (addressed.view) options.window.show(addressed.view)
    else if (options.window.moved.value) options.window.reset()
  }

  watch(() => route.query, read)
  watch(ready, (now) => { if (now) read() }, { immediate: true })
  watch([selectedIds, reach], () => write('push'))
  let pending: ReturnType<typeof setTimeout> | null = null
  watch(options.window.changes, () => {
    if (pending) clearTimeout(pending)
    pending = setTimeout(() => { pending = null; write('replace') }, 300)
  })

  return {
    /** The address of this reading, absolute, for *Copy link*. */
    link: (): string => new URL(router.resolve({ query: wanted() }).href, window.location.origin).href,
  }
}
