import type { Ref } from 'vue'

/** A diagram window's zoom, as its zoom cluster and its keys use it (`useFittedPanZoom` is one). */
export interface ViewportZoom {
  readonly scale: Ref<number>
  readonly zoomBy: (factor: number) => void
  /** Fit the diagram to the window again. */
  readonly resetView: () => void
}
