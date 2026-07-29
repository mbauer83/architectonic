/** Generic trailing-edge debouncer: each call cancels the previous pending timer and
 * schedules a fresh one — only the last call within `delayMs` of silence actually runs. */
export const createDebouncer = (delayMs: number): (fn: () => void) => void => {
  let timer: ReturnType<typeof setTimeout> | undefined
  return (fn: () => void): void => {
    if (timer !== undefined) clearTimeout(timer)
    timer = setTimeout(fn, delayMs)
  }
}
