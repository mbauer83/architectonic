<script setup lang="ts">
/**
 * Where the diagram sidebar sits: beside the canvas in the layout, or over it once the canvas has
 * taken the whole screen.
 *
 * Fullscreen is the browser's, on the canvas element (`useFullscreen`), and the browser paints
 * *nothing* outside that element — so a sidebar living in the layout's third grid column simply
 * vanishes on entry, and the reader loses the panel that explains whatever they just clicked. This
 * moves it inside the fullscreen element instead of hiding it, and reveals it on selection: over a
 * diagram filling the screen, a permanently docked panel is covering the drawing for no reason most
 * of the time.
 *
 * **`Teleport` with `:disabled`, not `v-if`/`v-else` over two positions.** Both would put the
 * sidebar in the right DOM place; only this one keeps the *same component instance* across the
 * move, so entering fullscreen does not remount the sidebar, re-run its entity query, and throw
 * away its scroll position. That is also why nothing is wrapped around the slot: the sidebar is
 * `position: sticky` as a grid child, and a wrapper would become the grid child instead, leaving
 * the sticky to resolve against a wrapper of its own height and quietly stop working.
 *
 * Presentation is not here. The two rules that place and animate the sidebar over a fullscreen
 * canvas are in `styles/shared.css`, keyed on `.img-container:fullscreen`, because the host element
 * is what supplies the positioning context and scoped styles cannot reach another component's root
 * anyway. One definition serves every view that docks a sidebar this way.
 */

defineProps<{
  /**
   * The element the browser has made fullscreen, and the sidebar's host while it is. `null` before
   * the canvas has mounted, which is also when there is nowhere to teleport to.
   */
  fullscreenHost: HTMLElement | null
  isFullscreen: boolean
  /** Whether anything is selected. Gates the fullscreen presentation only — never the docked one. */
  hasSelection: boolean
}>()
</script>

<template>
  <Teleport
    :to="fullscreenHost"
    :disabled="!isFullscreen || fullscreenHost === null"
  >
    <Transition
      name="sidebar-fly"
      appear
    >
      <slot v-if="!isFullscreen || hasSelection" />
    </Transition>
  </Teleport>
</template>
