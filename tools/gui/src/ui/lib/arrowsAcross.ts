/**
 * ← and → move the focus among the buttons of the group the key was pressed in, round from the last to
 * the first (sketch 01·7: the leave choice's three answers). The key is the group's: it goes no further.
 */
export const arrowsAcross = (event: KeyboardEvent): void => {
  const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
  const group = event.currentTarget
  if (step === 0 || !(group instanceof HTMLElement)) return
  const buttons = [...group.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
  if (buttons.length === 0) return
  event.preventDefault()
  event.stopPropagation()
  const found = buttons.findIndex((button) => button === document.activeElement)
  const at = found >= 0 ? found : step > 0 ? -1 : 0
  buttons[(at + step + buttons.length) % buttons.length].focus()
}
