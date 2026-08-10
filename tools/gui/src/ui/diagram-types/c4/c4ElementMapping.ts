import { graphvizMapElements } from '../../lib/graphvizElementMapping'
import type { DiagramElementMap, DiagramMapContext } from '../../lib/diagramViewerExtensions'

/**
 * Mapping a rendered C4 diagram's SVG back to model entities.
 *
 * The renderer names each element after its **local id**, not the entity's `display_alias`, so the
 * generic matcher — which builds its map from `display_alias` — resolved nothing: clicking selected
 * nothing, and because `useDiagramSvgSelection` returns early on an empty node map, the drill-down
 * badges never rendered either.
 *
 * The traversal was never the problem. `resolveNodeAlias` already reads the `data-qualified-name`
 * attribute PlantUML emits (`<g class="entity" data-qualified-name="SS_platform_0">` — there are no
 * `<g id>` and no `<title>` elements in a C4 render at all). Only the keys were missing. So this
 * contributes keys and delegates everything else, which keeps the C4 naming rule here where the
 * diagram type lives rather than in the generic matcher.
 */

/** Mirrors `_alias_for` in `src/diagram_types/c4/_c4_types.py` — the renderer's own rule. */
export const c4ItemAlias = (itemType: string, localId: string, index: number): string => {
  const normalized = localId.replace(/[^A-Za-z0-9_]/g, '_')
  const prefix = itemType
    .replace(/-/g, '_')
    .split('_')
    .map((part) => part.slice(0, 1).toUpperCase())
    .join('') || 'C'
  return `${prefix}_${normalized}_${index}`
}

/**
 * `alias → artifact_id` for every bound item in the payload.
 *
 * `index` is the item's position **within its own type array**, not a global counter — a real render
 * carries `P_planner_0`, `P_cnc_1`, `P_tadmin_2` beside `SS_platform_0`, `SS_auth0_1`: two
 * independent 0-based sequences. `entity_id` is present because the read envelope re-hydrates it
 * from the canonical `bindings:` block, which is where the correspondence lives on disk.
 */
export const c4AliasesFrom = (
  diagramEntities: Record<string, unknown> | undefined,
): Map<string, string> => {
  const aliases = new Map<string, string>()
  if (!diagramEntities) return aliases
  for (const [itemType, value] of Object.entries(diagramEntities)) {
    if (itemType.startsWith('_') || !Array.isArray(value)) continue
    value.forEach((raw, index) => {
      if (!raw || typeof raw !== 'object') return
      const item = raw as Record<string, unknown>
      const localId = typeof item.id === 'string' ? item.id : ''
      const entityId = typeof item.entity_id === 'string' ? item.entity_id : ''
      if (!localId || !entityId) return
      const authored = typeof item.alias === 'string' && item.alias ? item.alias.replace(/-/g, '_') : ''
      aliases.set(authored || c4ItemAlias(itemType, localId, index), entityId)
    })
  }
  return aliases
}

export const c4MapElements = (svgRoot: SVGSVGElement, ctx: DiagramMapContext): DiagramElementMap =>
  graphvizMapElements(svgRoot, ctx, c4AliasesFrom(ctx.diagramEntities))
