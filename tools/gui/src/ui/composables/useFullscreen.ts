import { onUnmounted, ref, type Ref } from 'vue'

/**
 * Native fullscreen for an element the caller owns.
 *
 * The browser's Fullscreen API rather than a CSS overlay pinned to the viewport: Esc-to-exit, the
 * exit affordance the browser puts up on entry, and restoring the page underneath are all things it
 * already does. An overlay would have to reimplement each of them, and the Esc half cannot be made
 * to work reliably from a component that does not hold focus.
 *
 * `isSupported` is read once, at setup: `fullscreenEnabled` answers a permissions-policy question
 * about the document, which does not change while the document is alive.
 */
export function useFullscreen(elementRef: Readonly<Ref<HTMLElement | null>>) {
  const isFullscreen = ref(false)
  const isSupported = document.fullscreenEnabled === true

  const syncFromDocument = () => {
    // The `element !== null` half is load-bearing. When the element leaves the document — a save
    // re-renders the page and the canvas goes with it — the browser exits fullscreen and fires this,
    // and by then the ref is `null` as well. `document.fullscreenElement === elementRef.value` was
    // then `null === null`, so the flag latched *on* with nothing to be fullscreen in.
    //
    // What that cost was not the flag: `FullscreenDock` shows its slot only when it is not fullscreen
    // or something is selected, and the same save clears the selection — so the sidebar stopped
    // rendering and did not come back until the page was reloaded by hand.
    const element = elementRef.value
    isFullscreen.value = element !== null && document.fullscreenElement === element
  }

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

  document.addEventListener('fullscreenchange', syncFromDocument)
  onUnmounted(() => {
    document.removeEventListener('fullscreenchange', syncFromDocument)
  })

  return { isFullscreen, isSupported, toggle }
}
