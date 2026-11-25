/**
 * The keys a diagram's window answers wherever its focus is inside it, in either mode (sketch 01·1,
 * 02·9): `0` fits, `+` and `−` zoom — `=` too on QWERTY (02·7) — and, in view mode, `E` edits (01·2).
 * Not in a text field, and not with a modifier but Shift.
 */
import { onBeforeUnmount, watch, type Ref } from 'vue'
import type { ViewportZoom } from '../components/viewportZoom'
import { viewportKeyOf } from '../lib/keyboardScheme'
import { useEditingPreferences } from './useEditingPreferences'

/** How far one press of `+` or `−` zooms. */
const KEY_STEP = 1.2

const typingIn = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

export function useCanvasHostKeys(
  host: Readonly<Ref<HTMLElement | null>>, zoom: () => ViewportZoom | undefined,
  /** Enter edit mode, where `E` may: null while it may not (edit mode itself, or a diagram not edited here). */
  edit: () => (() => void) | null = () => null,
) {
  const prefs = useEditingPreferences()
  const onKeydown = (event: KeyboardEvent) => {
    if (typingIn(event.target) || event.defaultPrevented) return
    const view = zoom()
    const command = view ? viewportKeyOf(event, prefs.scheme.value) : null
    const enter = (event.key === 'e' || event.key === 'E') && !event.ctrlKey && !event.metaKey && !event.altKey
      ? edit() : null
    if (command === null && enter === null) return
    event.preventDefault()
    if (command === 'fit') view?.resetView()
    else if (command !== null) view?.zoomBy(command === 'in' ? KEY_STEP : 1 / KEY_STEP)
    else enter?.()
  }
  watch(host, (element, previous) => {
    previous?.removeEventListener('keydown', onKeydown)
    element?.addEventListener('keydown', onKeydown)
  }, { immediate: true })
  onBeforeUnmount(() => host.value?.removeEventListener('keydown', onKeydown))
}
