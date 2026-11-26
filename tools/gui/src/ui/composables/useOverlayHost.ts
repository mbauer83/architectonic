import { computed, type Ref } from 'vue'
import { useFullscreenElement } from './useFullscreen'

/**
 * Where an overlay a canvas opens — its menu, its gesture cues, its details dialog — is teleported: into the
 * element that has the screen while one does, else the page's body.
 *
 * The browser paints nothing outside a fullscreen element (`useFullscreen`), so an overlay teleported to the
 * body opened, took the focus and could not be seen while the canvas filled the screen. The overlay keeps its
 * own fixed positioning, which a fullscreen element does not change.
 */
export function useOverlayHost(): Readonly<Ref<HTMLElement | 'body'>> {
  const holder = useFullscreenElement()
  return computed(() => holder.value ?? 'body')
}
