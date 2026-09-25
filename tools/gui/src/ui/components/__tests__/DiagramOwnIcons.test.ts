// @vitest-environment jsdom
//
// A diagram's own icons are listed with the way to move each into the library; a diagram with none
// shows nothing.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import DiagramOwnIcons from '../DiagramOwnIcons.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'

const WROTE = { wrote: true, path: 'x', artifact_id: 'ICO@1.logo01', content: null, warnings: [], verification: null }
const OWN = { icons: { logo: { name: 'Logo', 'png-base64': 'AAAA' } } }

let app: App | null = null
let host: HTMLDivElement

const mounted = (diagramEntities: Record<string, unknown>) => {
  const shareIcon = vi.fn(() => Effect.succeed(WROTE))
  const shared = vi.fn()
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(DiagramOwnIcons, { diagramId: 'ARC@1.view01', diagramEntities, onShared: shared }) })
  app.provide(modelServiceKey, { shareIcon } as unknown as ModelService)
  app.mount(host)
  return { shareIcon, shared }
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('a diagram’s own icons', () => {
  it('shows nothing for a diagram that holds none', () => {
    mounted({})

    expect(host.querySelector('.own-icons')).toBeNull()
  })

  it('moves one into the library with the attribution given', async () => {
    const { shareIcon, shared } = mounted(OWN)
    host.querySelector<HTMLButtonElement>('.own-icons li button')!.click()
    await nextTick()
    const input = host.querySelector<HTMLInputElement>('.share input')!
    input.value = 'Drawn here'
    input.dispatchEvent(new Event('input'))
    host.querySelector<HTMLFormElement>('.share')!.dispatchEvent(new Event('submit'))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    expect(shareIcon).toHaveBeenCalledWith('ARC@1.view01', 'logo', { attribution: 'Drawn here', dry_run: false })
    expect(shared).toHaveBeenCalled()
  })
})
