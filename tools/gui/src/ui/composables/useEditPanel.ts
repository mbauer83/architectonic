import { computed, ref } from 'vue'

/** Remembered per browser: a reader who closes the panel to arrange wants it closed next time too. */
const PANEL_KEY = 'arch_diagram_edit_panel'

const remembered = (): boolean | null => {
  try {
    const value = localStorage.getItem(PANEL_KEY)
    return value === null ? null : value === '1'
  } catch { return null }
}
const remember = (open: boolean): void => {
  try { localStorage.setItem(PANEL_KEY, open ? '1' : '0') } catch { /* storage refused: for this page only */ }
}

/**
 * The edit mode's panel beside the canvas (owner, Q22): open or closed from the panel icon at the end
 * of the edit bar. Arranging needs the canvas and adding needs the panel, so the reader decides, and
 * the choice is remembered per browser. Until it has been made once, a diagram too large to see whole
 * opens with the panel closed and any other with it open.
 */
export function useEditPanel(large: () => boolean) {
  const open = ref(true)
  return {
    open: computed(() => open.value),
    /** Edit mode was entered: the remembered choice, or the default for this diagram's size. */
    opened: () => { open.value = remembered() ?? !large() },
    toggle: () => { open.value = !open.value; remember(open.value) },
  }
}
