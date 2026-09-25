// @vitest-environment jsdom
//
// A row shows the icon its instance shows on this diagram, and opens the picker to change it — but
// only where the editing view provides icon editing, so every other list looks as it did.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, ref, type App } from 'vue'
import { Effect } from 'effect'
import EntitySelectionList from '../EntitySelectionList.vue'
import { diagramIconsKey, type DiagramIconEditing } from '../../composables/useDiagramIcons'
import { modelServiceKey } from '../../keys'
import type { EntityDisplayInfo } from '../../../domain'
import type { ModelService } from '../../../application/ModelService'

const NODE: EntityDisplayInfo = {
  artifact_id: 'NOD@1.aa.cluster', name: 'Cluster', artifact_type: 'technology-node', domain: 'technology',
  subdomain: '', status: 'active', display_alias: 'NOD_aa', element_type: 'node', element_label: 'Cluster',
  diagram_internal: false,
}
const PICTURE = 'data:image/png;base64,AAAA'
const MARK = { artifact_id: 'ICO@1.mark01', name: 'Mark', attribution: 'Here', applies_to: [], default_style: 'badge',
  tags: [], status: 'active', source_format: 'png', width: 32, height: 32, render_digest: 'sha256:a', is_global: false,
  baseline_standing: { kind: 'enterprise-baseline' } } as const

let app: App | null = null
let host: HTMLDivElement

const editing = (shown: boolean) => ({
  styles: ref(['badge', 'figure'] as const),
  shownFor: () => shown ? { icon: { icon: MARK.artifact_id, style: 'badge', level: 'type', picture: 'sha256:a' }, picture: PICTURE } : undefined,
  statedAt: () => ({}),
  choose: vi.fn<DiagramIconEditing['choose']>(),
  upload: vi.fn<DiagramIconEditing['upload']>(),
}) satisfies DiagramIconEditing

const mounted = (icons?: DiagramIconEditing) => {
  host = document.createElement('div')
  document.body.appendChild(host)
  const svc = {
    listIcons: vi.fn(() => Effect.succeed({ total: 1, items: [MARK] })),
    iconImageUrl: (id: string) => `/api/icons/${id}/image`,
  } as unknown as ModelService
  app = createApp({
    render: () => h(EntitySelectionList, {
      rows: [{ entity: NODE, occurrenceId: null }], candidateConnections: [], includedEntityIds: [NODE.artifact_id],
      includedConnectionIds: [], relatedEntitiesById: {}, expandedConnectionEntityIds: [], expandedRelatedEntityIds: [],
    }),
  })
  app.provide(modelServiceKey, svc)
  if (icons) app.provide(diagramIconsKey, icons)
  app.mount(host)
  return { host, svc }
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('the icon a row shows', () => {
  it('offers nothing where the view provides no icon editing', () => {
    const { host } = mounted()

    expect(host.querySelector('.icon-chip')).toBeNull()
  })

  it('shows the picture its instance shows, and says where it comes from', () => {
    const { host } = mounted(editing(true))
    const chip = host.querySelector<HTMLButtonElement>('.icon-chip')!

    expect(chip.querySelector('img')!.getAttribute('src')).toBe(PICTURE)
    expect(chip.title).toContain('all of its type here')
  })

  it('opens the picker, and a choice states the icon for this element', async () => {
    const icons = editing(false)
    const { host } = mounted(icons)
    host.querySelector<HTMLButtonElement>('.icon-chip')!.click()
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    host.querySelector<HTMLButtonElement>('.ip-entry')!.click()

    expect(icons.choose).toHaveBeenCalledWith(NODE.artifact_id, 'technology-node', 'instance', { icon: MARK.artifact_id })
    await nextTick()
    expect(host.querySelector('.icon-picker')).toBeNull()
  })
})
