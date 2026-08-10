/**
 * The C4 alias bridge, pinned against real renderer output.
 *
 * C4 element selection and drill-down were dead in the GUI: the SVG carries
 * `data-qualified-name="SS_platform_0"` — an alias built from the item's *local id* — while
 * `buildAliasToId` only ever held `display_alias`, the *model* alias (`APP_iVvOytl`). Nothing
 * matched, `nodes` stayed empty, and `useDiagramSvgSelection` returned early above the
 * badge-injection loop, so neither half worked.
 *
 * The literals below are taken from an actual rendered C4 L1 SVG, not invented, because the whole
 * defect was a mapping that looked reasonable and matched nothing the renderer emits.
 */
import { describe, expect, it } from 'vitest'

import { c4ItemAlias } from '../graphvizElementMapping'

describe('the alias the C4 renderer emits', () => {
  it('matches real rendered output for each item type', () => {
    // Observed in CSC@…c4-l1-up2parts-cloud-platform-in-context.svg.
    expect(c4ItemAlias('software-system', 'platform', 0)).toBe('SS_platform_0')
    expect(c4ItemAlias('person', 'planner', 0)).toBe('P_planner_0')
    expect(c4ItemAlias('software-system', 'auth0', 1)).toBe('SS_auth0_1')
  })

  it('indexes within the item type, not across the payload', () => {
    // The same render carries P_planner_0/P_cnc_1/P_tadmin_2 *and* SS_platform_0/SS_auth0_1 —
    // two independent 0-based sequences. A global counter would produce neither.
    expect(c4ItemAlias('person', 'cnc', 1)).toBe('P_cnc_1')
    expect(c4ItemAlias('person', 'tadmin', 2)).toBe('P_tadmin_2')
  })

  it('takes the prefix from the initials of each part of the item type', () => {
    expect(c4ItemAlias('container', 'api', 0)).toBe('C_api_0')
    expect(c4ItemAlias('component', 'repo', 0)).toBe('C_repo_0')
    expect(c4ItemAlias('', 'thing', 0)).toBe('C_thing_0')
  })

  it('normalises characters an alias may not carry, as the renderer does', () => {
    expect(c4ItemAlias('software-system', 'my-service.v2', 0)).toBe('SS_my_service_v2_0')
  })
})
