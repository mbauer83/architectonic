import { computed, onUnmounted, ref, watch, type ComputedRef, type Ref } from 'vue'

/**
 * The transform a pan/zoom viewport puts on its canvas, and `will-change` held only while the canvas
 * is actually moving.
 *
 * Two forms, because there are two kinds of content and scaling them the same way is wrong for one of
 * them. Arbitrary HTML has no size of its own to set, so it is scaled by the transform. An **SVG owns
 * its size**: giving it a `width`/`height` makes the browser lay its text out at the final size, where
 * scaling a wrapper instead rasterises a scaled layer — which renders the text blurry at best and, on
 * a large diagram at a small fit scale, left every element label unpainted until a pointer movement
 * invalidated the layer. So `usePanTranslateStyle` is for content that carries its own scale, and the
 * caller puts the scale where it belongs.
 *
 * Both diagram viewports built this same style object, and both declared `will-change: transform`
 * permanently. That is the documented anti-pattern for the property: it exists to warn the browser
 * *just before* a change, and a permanent declaration instead keeps the element on its own
 * compositing layer for the life of the page. The cost showed up as a rendering fault rather than as
 * slowness — a diagram's labels missing until the pointer moved over it. The glyphs were in the DOM,
 * visible, opaque and correctly sized; the layer they belonged to had simply not been rasterised with
 * them, and any later invalidation — a hover, a scroll — brought them in. A scaled SVG's text is what
 * suffers, which is why a diagram showed it and the boxes did not.
 *
 * So the hint is applied on the first change to the transform and dropped a short while after the
 * last one, which is what the property is for and what returns the canvas to ordinary painting while
 * a reader is reading rather than dragging.
 *
 * One helper rather than the fix twice: the two viewports' styles were character-identical, so a
 * second copy of this reasoning is a second copy to forget.
 */

/**
 * How long after the last transform change the hint is kept.
 *
 * Long enough to span the gaps between wheel events in one zoom gesture and the pause between two
 * drags, so a reader working the view is not paying for a layer being created and destroyed under
 * them; short enough that a reader who has stopped is looking at a normally painted diagram.
 */
const SETTLE_MS = 400

interface PanStyle {
  readonly canvasStyle: ComputedRef<Record<string, string>>
}

/** The `will-change` hint, on from the first change and off a short while after the last. */
const useSettling = (sources: Readonly<Ref<number>>[]) => {
  const settling = ref(false)
  // Bare timers rather than `window.setTimeout`: nothing here touches a document, so requiring a
  // `window` would only have made the composable untestable without one.
  let timer: ReturnType<typeof setTimeout> | undefined

  watch(sources, () => {
    settling.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { settling.value = false }, SETTLE_MS)
  })

  onUnmounted(() => clearTimeout(timer))
  return settling
}

/** Omitted rather than set to `auto` when idle: `auto` is the initial value, and writing it leaves the
 * declaration in the style attribute for a reader of the DOM to wonder about. */
const hint = (settling: boolean): Record<string, string> =>
  settling ? { willChange: 'transform' } : {}

/** For content with no size of its own: the scale goes in the transform. */
export const usePanCanvasStyle = (
  scale: Readonly<Ref<number>>,
  tx: Readonly<Ref<number>>,
  ty: Readonly<Ref<number>>,
): PanStyle => {
  const settling = useSettling([scale, tx, ty])
  return {
    canvasStyle: computed(() => ({
      transform: `translate(${tx.value}px, ${ty.value}px) scale(${scale.value})`,
      transformOrigin: '0 0',
      ...hint(settling.value),
      display: 'inline-block',
    })),
  }
}

/** For content that carries its own scale — an SVG the caller sizes. Translation only. */
export const usePanTranslateStyle = (
  tx: Readonly<Ref<number>>,
  ty: Readonly<Ref<number>>,
): PanStyle => {
  const settling = useSettling([tx, ty])
  return {
    canvasStyle: computed(() => ({
      transform: `translate(${tx.value}px, ${ty.value}px)`,
      transformOrigin: '0 0',
      ...hint(settling.value),
      display: 'inline-block',
    })),
  }
}
