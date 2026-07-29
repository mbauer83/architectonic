// @vitest-environment jsdom
//
// Regression for the stale-tier refetch race: selecting a tier navigates via
// router.replace (async), so the derived `tier` computed updates on the NEXT
// tick — a synchronous load() inside selectTier fetched with the pre-navigation
// tier and left the list unfiltered. The fix refetches from a `watch(tier)`
// after the route updates. This drives the real composable through a real
// memory-history router and records the scope each list call carried; the LAST
// call must reflect the newly selected Enterprise tier (scope=global).
import { beforeAll, describe, it, expect } from 'vitest'
import { createApp, defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { Effect } from 'effect'
import { useDocumentsListState } from '../useDocumentsListState'
import { useDiagramsListState } from '../useDiagramsListState'

class StubEventSource {
  addEventListener() {}
  close() {}
}

beforeAll(() => {
  ;(globalThis as unknown as { EventSource: unknown }).EventSource = StubEventSource
})

const mountWithRouter = async (setup: () => { selectTier: (t: 'enterprise') => void }) => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  let api: { selectTier: (t: 'enterprise') => void } | null = null
  const Host = defineComponent({
    setup() {
      api = setup()
      return () => h('div')
    },
  })
  const app = createApp({ render: () => h(Host) })
  app.use(router)
  app.mount(document.createElement('div'))
  await nextTick()

  api!.selectTier('enterprise')
  await new Promise((resolve) => setTimeout(resolve, 50))
  await nextTick()

  app.unmount()
  return router
}

describe('tier facet refetch uses the NEW tier, not the stale one', () => {
  it('documents: selecting Enterprise refetches with scope=global', async () => {
    const scopes: (string | undefined)[] = []
    const svc = {
      listDocumentTypes: () => Effect.succeed([]),
      listGroups: () => Effect.succeed({}),
      listDocuments: (params?: { scope?: string }) => {
        scopes.push(params?.scope)
        return Effect.succeed({ total: 0, items: [] })
      },
    } as never

    await mountWithRouter(() => useDocumentsListState(svc))
    // First fetch is All (no scope); the tier watcher's refetch after navigation
    // carries the NEW enterprise tier — a synchronous stale-tier load would have
    // left the last scope undefined.
    expect(scopes).toContain('global')
    expect(scopes.at(-1)).toBe('global')
  })

  it('diagrams: selecting Enterprise refetches with scope=global', async () => {
    const scopes: (string | undefined)[] = []
    const svc = {
      listDiagramTypes: () => Effect.succeed([]),
      listGroups: () => Effect.succeed({}),
      listDiagrams: (params?: { scope?: string }) => {
        scopes.push(params?.scope)
        return Effect.succeed({ total: 0, items: [] })
      },
    } as never

    await mountWithRouter(() => useDiagramsListState(svc))
    expect(scopes).toContain('global')
    expect(scopes.at(-1)).toBe('global')
  })
})
