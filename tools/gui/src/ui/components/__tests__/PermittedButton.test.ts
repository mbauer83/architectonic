// @vitest-environment jsdom
/** A write button is offered as the permission answer allows its operation, and says why where it does not. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import PermittedButton from '../PermittedButton.vue'
import { answered } from '../../composables/__tests__/permissionFixtures'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.innerHTML = '' })

const mounted = async (refused: readonly string[], props: Record<string, unknown> = {}) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const click = vi.fn()
  app = answered(createApp({
    render: () => h(PermittedButton, { operation: 'candidates_apply_candidate', title: 'Apply it', onClick: click, ...props },
      () => 'Apply'),
  }), refused)
  app.mount(host)
  await nextTick()
  return { button: host.querySelector('button')!, click }
}

describe('a button that writes', () => {
  it('is offered, with its own title, where the operation is allowed', async () => {
    const { button, click } = await mounted([])
    expect(button.disabled).toBe(false)
    expect(button.title).toBe('Apply it')
    button.click()
    expect(click).toHaveBeenCalled()
  })

  it('is disabled with the reason as its title where the operation is refused', async () => {
    const { button } = await mounted(['candidates_apply_candidate'])
    expect(button.disabled).toBe(true)
    expect(button.title).toBe('Not permitted for your role')
  })

  it('stays disabled for the caller\'s own reason', async () => {
    const { button } = await mounted([], { disabled: true })
    expect(button.disabled).toBe(true)
  })
})
