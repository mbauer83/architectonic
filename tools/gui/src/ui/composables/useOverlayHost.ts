import { onUnmounted, shallowRef, type Ref } from 'vue'

/**
 * Where an overlay a canvas opens — its menu, its gesture cues, its details dialog — is teleported: into the
 * element that has the screen while one does, else the page's body.
 *
 * The browser paints nothing outside a fullscreen element (`useFullscreen`), so an overlay teleported to the
 * body opened, took the focus and could not be seen while the canvas filled the screen. The overlay keeps its
 * own fixed positioning, which a fullscreen element does not change.
 */
export function useOverlayHost(): Readonly<Ref<HTMLElement | 'body'>> {
  const current = (): HTMLElement | 'body' =>
    document.fullscreenElement instanceof HTMLElement ? document.fullscreenElement : 'body'
  const host = shallowRef(current())
  const sync = () => { host.value = current() }
  document.addEventListener('fullscreenchange', sync)
  onUnmounted(() => { document.removeEventListener('fullscreenchange', sync) })
  return host
}
