// @vitest-environment jsdom
//
// jsdom is required only to IMPORT the app router (createWebHistory reads
// window.location at construction); navigation itself runs on memory history.
import { describe, it, expect } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { router } from '../index'

/** Same route table as the app, on memory history so redirects can be exercised
 * by real navigation (resolve() alone never applies redirect records). */
const makeTestRouter = () =>
  createRouter({ history: createMemoryHistory(), routes: router.options.routes })

describe('legacy /global deep links redirect to faceted routes', () => {
  it('/global/entities preserves query and hash while adding tier=enterprise', async () => {
    const testRouter = makeTestRouter()
    await testRouter.push('/global/entities?domain=motivation&view=treemap#catalog')
    expect(testRouter.currentRoute.value.path).toBe('/entities')
    expect(testRouter.currentRoute.value.query).toEqual({
      domain: 'motivation',
      view: 'treemap',
      tier: 'enterprise',
    })
    expect(testRouter.currentRoute.value.hash).toBe('#catalog')
  })

  it('/global/diagrams preserves query while adding tier=enterprise', async () => {
    const testRouter = makeTestRouter()
    await testRouter.push('/global/diagrams?type=archimate&group=x')
    expect(testRouter.currentRoute.value.path).toBe('/diagrams')
    expect(testRouter.currentRoute.value.query).toEqual({ type: 'archimate', group: 'x', tier: 'enterprise' })
  })

  it('back/forward across the redirect returns to the faceted route', async () => {
    const testRouter = makeTestRouter()
    await testRouter.push('/documents')
    await testRouter.push('/global/entities?domain=motivation')
    testRouter.back()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(testRouter.currentRoute.value.path).toBe('/documents')
    testRouter.forward()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(testRouter.currentRoute.value.path).toBe('/entities')
    expect(testRouter.currentRoute.value.query.tier).toBe('enterprise')
  })

  it('a copied faceted URL navigates unchanged', async () => {
    const testRouter = makeTestRouter()
    await testRouter.push('/entities?tier=enterprise&domain=motivation')
    expect(testRouter.currentRoute.value.path).toBe('/entities')
    expect(testRouter.currentRoute.value.query).toEqual({ tier: 'enterprise', domain: 'motivation' })
  })

  it('/global/search keeps its plain redirect', async () => {
    const testRouter = makeTestRouter()
    await testRouter.push('/global/search')
    expect(testRouter.currentRoute.value.path).toBe('/search')
  })
})
