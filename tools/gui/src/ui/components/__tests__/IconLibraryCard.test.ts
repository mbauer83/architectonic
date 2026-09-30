// @vitest-environment jsdom
//
// A library icon this repository owns can be edited, retired, replaced and deleted; an enterprise one is
// only shown. A refusal — deleting an icon a diagram shows — is said on the card, in the server's words.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { Effect } from 'effect'
import IconLibraryCard from '../IconLibraryCard.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'
import type { IconSummary } from '../../../domain/schemas/icons'

const ICON: IconSummary = {
  artifact_id: 'ICO@1.mark01', name: 'Mark', attribution: 'Here', applies_to: [], default_style: 'badge', tags: [],
  status: 'active', source_format: 'png', width: 32, height: 32, render_digest: 'sha256:a', is_global: false,
  baseline_standing: { kind: 'enterprise-baseline' }, used_on: [], default_for: [],
}
const WROTE = { wrote: true, path: 'x', artifact_id: ICON.artifact_id, content: null, warnings: [], verification: null }
const IN_USE = JSON.stringify({ detail: { code: 'conflict', message: 'ICO@1.mark01 is still used by diagrams ARC@1.view01' } })

let app: App | null = null
let host: HTMLDivElement

const settle = async (): Promise<void> => {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

const mounted = (icon: IconSummary, svc: Partial<ModelService>) => {
  const changed = vi.fn()
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(IconLibraryCard, { icon, others: [], onChanged: changed }) })
  app.provide(modelServiceKey, { iconImageUrl: () => '/img', ...svc } as ModelService)
  app.use(createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { render: () => null } }] }))
  app.mount(host)
  return { changed }
}

const button = (label: string): HTMLButtonElement =>
  [...host.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('a library icon', () => {
  it('offers nothing to change when the enterprise holds it', () => {
    mounted({ ...ICON, is_global: true }, {})

    expect(host.querySelector('.actions')).toBeNull()
    expect(host.textContent).toContain('Enterprise')
  })

  it('is retired by an edit of its status', async () => {
    const editIcon = vi.fn(() => Effect.succeed(WROTE))
    const { changed } = mounted(ICON, { editIcon })

    button('Retire').click()
    await settle()

    expect(editIcon).toHaveBeenCalledWith(ICON.artifact_id, { status: 'retired', dry_run: false })
    expect(changed).toHaveBeenCalled()
  })

  it('says why a delete was refused', async () => {
    const deleteIcon = vi.fn(() => Effect.fail(new Error(IN_USE)))
    const { changed } = mounted(ICON, { deleteIcon } as unknown as Partial<ModelService>)

    button('Delete').click()
    await settle()

    expect(host.querySelector('[role=alert]')!.textContent).toContain('still used by diagrams ARC@1.view01')
    expect(changed).not.toHaveBeenCalled()
  })

  it('names the diagrams that show it, and offers no delete while any does', () => {
    mounted({ ...ICON, used_on: [{ artifact_id: 'ARC@1.view01', name: 'Landscape' }] }, {})

    const link = host.querySelector<HTMLAnchorElement>('.usage a')!
    expect(link.textContent?.trim()).toBe('Landscape')
    expect(link.getAttribute('href')).toBe('/diagrams/ARC%401.view01')
    expect(button('Delete').disabled).toBe(true)
  })

  it('says it is shown nowhere, and may be deleted', () => {
    mounted(ICON, {})

    expect(host.querySelector('.usage')!.textContent).toContain('Not shown on any diagram')
    expect(button('Delete').disabled).toBe(false)
  })
})
