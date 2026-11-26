// @vitest-environment jsdom
/**
 * A new candidate is defined on its own canvas (owner, 2026-11-26): it starts empty and needs only a
 * name. A diagram, or another candidate to stack on, is an optional seed. The regression: the form
 * started on "what a diagram draws" and kept Create disabled until a diagram or a parent was chosen.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, nextTick, type App } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { Effect } from 'effect'
import type { ModelService } from '../../../application/ModelService'
import { modelServiceKey } from '../../keys'
import CandidateArchitecturesView from '../CandidateArchitecturesView.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

const settle = async () => {
  for (let turn = 0; turn < 5; turn++) await new Promise((resolve) => setTimeout(resolve, 0))
}

const mounted = async () => {
  const created: Readonly<Record<string, unknown>>[] = []
  const svc = {
    listCandidates: () => Effect.succeed([]),
    listDiagrams: () => Effect.succeed({ items: [] }),
    listDiagramTypes: () => Effect.succeed([]),
    createCandidate: (record: Readonly<Record<string, unknown>>) => {
      created.push(record)
      return Effect.succeed({ record: { id: 'CAN@1.a' } })
    },
  } as unknown as ModelService
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/candidates', component: CandidateArchitecturesView },
      { path: '/:rest(.*)*', component: defineComponent({ render: () => null }) },
    ],
  })
  await router.push('/candidates')
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(RouterView) })
  app.provide(modelServiceKey, svc)
  app.use(router)
  app.mount(host)
  await settle()
  const find = <T extends HTMLElement>(id: string) => host.querySelector<T>(`[data-testid="${id}"]`)
  find<HTMLButtonElement>('new-candidate')?.click()
  await nextTick()
  return { find, created, router }
}

const named = async (find: Awaited<ReturnType<typeof mounted>>['find'], name: string) => {
  const input = find<HTMLInputElement>('candidate-name')!
  input.value = name
  input.dispatchEvent(new Event('input'))
  await nextTick()
}

describe('a new candidate', () => {
  it('starts empty, with no seed chosen', async () => {
    const { find } = await mounted()
    expect(find<HTMLInputElement>('candidate-origin-empty')?.checked).toBe(true)
    expect(find('candidate-diagram')).toBeNull()
  })

  it('can be created with just a name, and is created empty', async () => {
    const { find, created, router } = await mounted()
    expect(find<HTMLButtonElement>('candidate-create')?.disabled).toBe(true)
    await named(find, 'Cached index store')
    expect(find<HTMLButtonElement>('candidate-create')?.disabled).toBe(false)

    find<HTMLFormElement>('new-candidate-form')?.dispatchEvent(new Event('submit', { cancelable: true }))
    await settle()

    expect(created).toEqual([{ name: 'Cached index store' }])
    expect(router.currentRoute.value.path).not.toBe('/candidates')
  })

  it('still asks for the diagram once seeding from one is chosen', async () => {
    const { find } = await mounted()
    await named(find, 'Cached index store')
    find<HTMLInputElement>('candidate-origin-diagram')?.click()
    await nextTick()
    expect(find('candidate-diagram')).not.toBeNull()
    expect(find<HTMLButtonElement>('candidate-create')?.disabled).toBe(true)
  })
})
