// @vitest-environment jsdom
//
// The picker states a choice at the scope and in the style the author picked, offers only the library
// icons that apply to the element, and turns a dropped-in file into an upload for this diagram.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import IconPicker from '../IconPicker.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'

const MARK = { artifact_id: 'ICO@1.mark01', name: 'Mark', attribution: 'Here', applies_to: [], default_style: 'badge',
  tags: [], status: 'active', source_format: 'png', width: 32, height: 32, render_digest: 'sha256:a', is_global: false,
  baseline_standing: { kind: 'enterprise-baseline' } } as const

let app: App | null = null
let host: HTMLDivElement

const settle = async (): Promise<void> => {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

const mounted = async (current: Record<string, unknown> = {}) => {
  const chosen: unknown[][] = []
  const uploaded: unknown[][] = []
  const listIcons = vi.fn(() => Effect.succeed({ total: 1, items: [MARK] }))
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({
    render: () => h(IconPicker, {
      elementName: 'Cluster', typeName: 'technology-node', applicableTo: 'NOD@1.aa', styles: ['badge', 'figure'], current,
      onChoose: (...args: unknown[]) => chosen.push(args), onUpload: (...args: unknown[]) => uploaded.push(args),
    }),
  })
  app.provide(modelServiceKey, { listIcons, iconImageUrl: () => '/img' } as unknown as ModelService)
  app.mount(host)
  await settle()
  return { chosen, uploaded, listIcons }
}

const pick = (value: string): void => {
  const radio = host.querySelector<HTMLInputElement>(`input[type=radio][value="${value}"]`)!
  radio.checked = true
  radio.dispatchEvent(new Event('change'))
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('choosing an icon', () => {
  it('asks the library for what applies to the element', async () => {
    const { listIcons } = await mounted()

    expect(listIcons).toHaveBeenCalledWith({ applicable_to: 'NOD@1.aa', q: undefined })
  })

  it('states it for every element of the type, in the style picked', async () => {
    const { chosen } = await mounted()
    pick('type')
    pick('figure')
    await nextTick()

    host.querySelector<HTMLButtonElement>('.ip-entry')!.click()

    expect(chosen).toEqual([['type', { icon: MARK.artifact_id, style: 'figure' }]])
  })

  it('clears only what is stated at the scope shown', async () => {
    const { chosen } = await mounted({ instance: { icon: MARK.artifact_id } })

    host.querySelector<HTMLButtonElement>('.ip-clear')!.click()

    expect(chosen).toEqual([['instance', null]])
  })

  it('turns a chosen file into an upload named after it', async () => {
    const { uploaded } = await mounted()
    const input = host.querySelector<HTMLInputElement>('input[type=file]')!
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'azure_kubernetes-service.png', { type: 'image/png' })
    Object.defineProperty(input, 'files', { value: [file] })
    input.dispatchEvent(new Event('change'))
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(uploaded).toEqual([[
      'instance', { name: 'azure kubernetes service', content_base64: 'iVBORw==', source_format: 'png' }, undefined,
    ]])
  })
})
