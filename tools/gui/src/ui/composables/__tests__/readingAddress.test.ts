// @vitest-environment jsdom
//
// The reading in the page's address: a new selection or reach adds a history entry, so Back returns to
// the previous reading; moving the window replaces the entry; a link read back selects what it names.

import { describe, expect, it } from 'vitest'
import { createApp, defineComponent, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter, useRoute, useRouter } from 'vue-router'
import { DEFAULT_REACH, type Reach, type ReadingView } from '../../../domain/diagramReading'
import { useReadingAddress } from '../useReadingAddress'

const A = 'BOB@1712870400.aaaaaa.a-thing'
const B = 'ACT@1712870400.bbbbbb.b-thing'

const settle = async () => {
  for (let i = 0; i < 4; i += 1) await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

const harness = async (start = '/diagrams/D') => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/diagrams/:id', component: { render: () => null } }],
  })
  await router.push(start)
  const selectedIds = ref<readonly string[]>([])
  const reach = ref<Reach>(DEFAULT_REACH)
  const moved = ref(false)
  const shown: ReadingView[] = []
  let address!: ReturnType<typeof useReadingAddress>
  const app = createApp(defineComponent({
    setup() {
      address = useReadingAddress({
        route: useRoute(), router: useRouter(), ready: ref(true), selectedIds, reach,
        drawnIds: () => [A, B], select: (ids) => { selectedIds.value = ids },
        window: {
          moved, current: () => ({ x: 10, y: 20, percent: 50 }),
          show: (view) => { shown.push(view); moved.value = true },
          reset: () => { moved.value = false }, changes: () => moved.value,
        },
      })
      return () => null
    },
  }))
  app.use(router)
  app.mount(document.createElement('div'))
  await router.isReady()
  await settle()
  return { router, selectedIds, reach, moved, shown, link: () => address.link() }
}

describe('the reading in the address', () => {
  it('writes the selection and reach, and Back returns to the reading before', async () => {
    const { router, selectedIds, reach } = await harness()
    selectedIds.value = [A]
    await settle()
    expect(router.currentRoute.value.query).toEqual({ focus: 'BOB@1712870400.aaaaaa', reach: 'in:1,out:1' })

    reach.value = { incoming: 0, outgoing: 'all' }
    await settle()
    selectedIds.value = [B]
    await settle()
    expect(router.currentRoute.value.query.focus).toBe('ACT@1712870400.bbbbbb')

    router.back()
    await settle()
    expect(selectedIds.value).toEqual([A])
    expect(reach.value).toEqual({ incoming: 0, outgoing: 'all' })
    router.back()
    await settle()
    expect(reach.value).toEqual(DEFAULT_REACH)
  })

  it('reads a pasted link: selects what it names, and shows its window', async () => {
    const { selectedIds, reach, shown, link } = await harness(
      '/diagrams/D?focus=ACT@1712870400.bbbbbb,XYZ@1.gone&reach=in:2,out:0&view=5,6,70')
    expect(selectedIds.value).toEqual([B])
    expect(reach.value).toEqual({ incoming: 2, outgoing: 0 })
    expect(shown).toEqual([{ x: 5, y: 6, percent: 70 }])
    expect(link()).toContain('/diagrams/D?focus=ACT@1712870400.bbbbbb&reach=in:2,out:0&view=10,20,50')
  })

  it('replaces the entry when only the window moves', async () => {
    const { router, selectedIds, moved } = await harness()
    selectedIds.value = [A]
    await settle()
    moved.value = true
    await new Promise((resolve) => setTimeout(resolve, 350))
    await settle()
    expect(router.currentRoute.value.query.view).toBe('10,20,50')

    // One Back leaves the reading altogether: the window's move took no entry of its own.
    router.back()
    await settle()
    expect(router.currentRoute.value.query).toEqual({})
    expect(selectedIds.value).toEqual([])
    expect(moved.value).toBe(false)
  })
})
