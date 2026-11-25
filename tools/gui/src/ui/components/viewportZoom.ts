import type { Ref } from 'vue'

/** A diagram window's zoom, as its zoom cluster and its keys use it (`useFittedPanZoom` is one). */
export interface ViewportZoom {
  readonly scale: Ref<number>
  readonly zoomBy: (factor: number) => void
  /** Back to the framing the window opened on. */
  readonly resetView: () => void
  /** The whole diagram in the window, however small: what a large diagram does not open on (Q19). */
  readonly fitWhole: () => void
}
