/**
 * The layout lab's GUI addresses: the bench with no diagram chosen, and one diagram on it, addressed
 * by path as identity must be. The route is declared whether or not the backend serves the lab — the
 * page itself says the lab is off — so only the menu entry follows the flag (`HttpLayoutLab`).
 */
import { describe, expect, it } from 'vitest'
import { ROUTE_TEMPLATES, layoutLabRoute } from './artifactRoutes'
import { modelRoutes } from './modelRoutes'

describe('the layout lab routes', () => {
  it('addresses the bench, and a diagram on it by its encoded id', () => {
    expect(layoutLabRoute()).toBe('/layout-lab')
    expect(layoutLabRoute('')).toBe('/layout-lab')
    expect(layoutLabRoute('ARC@1784483951.yBNaaU.strategy-overview')).toBe(
      '/layout-lab/ARC%401784483951.yBNaaU.strategy-overview',
    )
  })

  it('declares both addresses in the route table', () => {
    const paths = modelRoutes.map((route) => route.path)
    expect(paths).toContain(ROUTE_TEMPLATES.layoutLab)
    expect(paths).toContain(ROUTE_TEMPLATES.layoutLabDiagram)
  })
})
