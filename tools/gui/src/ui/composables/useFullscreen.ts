import { computed, shallowRef, watch, type Ref } from 'vue'

/**
 * Native fullscreen, and which element has the screen: the one place the GUI listens for it.
 *
 * The browser's Fullscreen API rather than a CSS overlay pinned to the viewport: Esc-to-exit, the
 * exit affordance the browser puts up on entry, and restoring the page underneath are all things it
 * already does. An overlay would have to reimplement each of them, and the Esc half cannot be made
 * to work reliably from a component that does not hold focus.
 *
 * One listener on the document keeps `screenHolder`; every reader — a canvas's own flag
 * (`useFullscreen`), where its overlays open (`useOverlayHost`) — is a projection of it, followed for as
 * long as the reader's component lives.
 */
const screenHolder = shallowRef<HTMLElement | null>(null)
let listening = false

const syncFromDocument = () => {
  const holder = document.fullscreenElement
  screenHolder.value = holder instanceof HTMLElement ? holder : null
}

/** The element that has the screen now, or null; followed until the calling component unmounts. */
export function useFullscreenElement(): Readonly<Ref<HTMLElement | null>> {
  if (!listening) {
    document.addEventListener('fullscreenchange', syncFromDocument)
    listening = true
  }
  syncFromDocument()
  const seen = shallowRef(screenHolder.value)
  // Synchronous, so a reader sees the change the moment the browser reports it; stopped with its component.
  watch(screenHolder, (holder) => { seen.value = holder }, { flush: 'sync' })
  return seen
}

/**
 * Native fullscreen for an element the caller owns.
 *
 * `isSupported` is read once, at setup: `fullscreenEnabled` answers a permissions-policy question
 * about the document, which does not change while the document is alive.
 */
export function useFullscreen(elementRef: Readonly<Ref<HTMLElement | null>>) {
  const holder = useFullscreenElement()
  const isSupported = document.fullscreenEnabled === true

  // The `element !== null` half is load-bearing. When the element leaves the document — a save
  // re-renders the page and the canvas goes with it — the browser exits fullscreen and reports no
  // holder, and by then the ref is `null` as well. Comparing the two alone read `null === null`, so the
  // flag latched *on* with nothing to be fullscreen in.
  //
  // What that cost was not the flag: `FullscreenDock` shows its slot only when it is not fullscreen
  // or something is selected, and the same save clears the selection — so the sidebar stopped
  // rendering and did not come back until the page was reloaded by hand.
  const isFullscreen = computed(() => elementRef.value !== null && holder.value === elementRef.value)

  const toggle = async (): Promise<void> => {
    if (!isSupported) return
    if (document.fullscreenElement !== null) {
      await document.exitFullscreen()
      return
    }
    // Rejects when the gesture that reached here was not user-initiated, or when a permissions
    // policy forbids it. Neither deserves an error banner — the control simply does nothing.
    await elementRef.value?.requestFullscreen().catch(() => {})
  }

  return { isFullscreen, isSupported, toggle }
}
