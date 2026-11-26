// @vitest-environment jsdom
/**
 * A viewpoint's Edit and Delete are offered by the permission answer for their own operations.
 *
 * Regression: the viewpoint pages and the document form read a write-block switch injected with a
 * default of "not blocked", so mounted without the app shell every write was offered. The row now asks
 * `useCan`, which refuses until the backend has answered.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import ViewpointCatalogRow from '../ViewpointCatalogRow.vue'
import { answered } from '../../composables/__tests__/permissionFixtures'
import { viewpointEnvelope } from '../../__tests__/viewpointFixtures'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.innerHTML = '' })

const definition = viewpointEnvelope({ slug: 'capability-map', tier: 'engagement' })

const buttons = async (provide: (one: App) => App) => {
  const host = document.createElement('table')
  const body = document.createElement('tbody')
  host.appendChild(body)
  document.body.appendChild(host)
  app = provide(createApp({
    render: () => h(ViewpointCatalogRow, { def: definition, pinned: false, scopeExpanded: false }),
  }))
  app.mount(body)
  await nextTick()
  const named = (label: string) => [...body.querySelectorAll('button')].find((one) => one.textContent?.trim() === label)!
  return { edit: named('Edit'), remove: named('Delete') }
}

describe('a viewpoint row', () => {
  it('refuses Edit and Delete before the backend has answered', async () => {
    const { edit, remove } = await buttons((one) => one)
    expect([edit.disabled, remove.disabled]).toEqual([true, true])
    expect(edit.title).toBe('Waiting for the backend to say what may be changed')
  })

  it('offers each by its own operation', async () => {
    const { edit, remove } = await buttons((one) => answered(one, ['viewpoints_delete_viewpoint']))
    expect([edit.disabled, remove.disabled]).toEqual([false, true])
    expect(remove.title).toBe('Not permitted for your role')
  })
})
