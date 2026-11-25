/**
 * A control that pulses once when what it shows changes in a way worth noticing (sketch 01·4, 03·10):
 * the layout chip when the picture is taken over, the count beside Save when a change joins it. The
 * pulse is a class the stylesheet animates, and drops under reduced motion; it is taken off when its
 * animation ends, so the next change pulses again.
 */
import { nextTick, ref, watch } from 'vue'

export function usePulse<Value>(
  watched: () => Value, worthIt: (now: Value, was: Value) => boolean = (now, was) => now !== was,
) {
  const pulsing = ref(false)
  watch(watched, async (now, was) => {
    if (!worthIt(now, was)) return
    pulsing.value = false
    await nextTick()
    pulsing.value = true
  })
  const settle = () => { pulsing.value = false }
  return { pulsing, settle }
}
