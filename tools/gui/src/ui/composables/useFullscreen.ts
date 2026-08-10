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
    isFullscreen.value = document.fullscreenElement === elementRef.value
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
