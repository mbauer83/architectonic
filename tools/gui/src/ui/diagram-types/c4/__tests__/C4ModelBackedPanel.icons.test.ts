// @vitest-environment jsdom
//
// A derived entity shows the icon it shows on the diagram, and the server is told the C4 type it is
// drawn as, so an icon stated for that type is the one the row shows.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, ref, type App } from 'vue'
import { Effect } from 'effect'
import C4ModelBackedPanel from '../C4ModelBackedPanel.vue'
import { diagramIconsKey, type DiagramIconEditing } from '../../../composables/useDiagramIcons'
import { modelServiceKey } from '../../../keys'
import type { DiagramOwnEntityTypeUiConfig, EntityDisplayInfo } from '../../../../domain'
import type { EntityTypeName } from '../../../../domain/types.generated'
import type { ModelService } from '../../../../application/ModelService'

const entity = (id: string, type: EntityTypeName, name: string): EntityDisplayInfo => ({
  artifact_id: id, name, artifact_type: type, domain: 'application', subdomain: '', status: 'active',
  display_alias: '', element_type: type, element_label: name, diagram_internal: false,
})
const container = (): DiagramOwnEntityTypeUiConfig => ({
  entity_type: 'container', label: 'Container', plural: 'Containers', min: 0, max: null, mapping_required: false,
  permitted_mappings: { entity_types: ['application-component'], entity_classes: [], sources: [] }, properties: [],
  classes: [], create_when: '', never_create_when: '', permitted_connections: [], required_connections: [],
  managed_fields: null, identity_scope: 'diagram', id_prefix: null, include_in_global_search: false,
  editable_metadata: { entity: [], subparts: {} },
})

const SCOPE = entity('APP@1.scope', 'application-component', 'Shop')
const API = entity('APP@2.api', 'application-component', 'Orders API')
const ODD = entity('DOB@3.odd', 'data-object', 'Ledger')

let app: App | null = null
let host: HTMLDivElement

const editing = (): DiagramIconEditing => ({
  register: vi.fn<DiagramIconEditing['register']>(() => () => undefined),
  styles: ref(['badge', 'figure'] as const),
  shownFor: () => undefined,
  statedAt: () => ({}),
  choose: vi.fn<DiagramIconEditing['choose']>(),
  upload: vi.fn<DiagramIconEditing['upload']>(),
})

const mounted = (icons?: DiagramIconEditing) => {
  host = document.createElement('div')
  document.body.appendChild(host)
  const svc = {
    listIcons: vi.fn(() => Effect.succeed({ total: 0, items: [] })),
    iconImageUrl: (id: string) => `/api/icons/${id}/image`,
  } as unknown as ModelService
  app = createApp({
    render: () => h(C4ModelBackedPanel, {
      entities: [SCOPE, API, ODD], diagramConnections: [], scopeEntityId: SCOPE.artifact_id,
      diagramOnlyTypes: [container()], diagramEntities: {}, scopeType: 'software-system',
    }),
  })
  app.provide(modelServiceKey, svc)
  if (icons) app.provide(diagramIconsKey, icons)
  app.mount(host)
  return host
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('the icon a derived entity shows', () => {
  it('offers nothing where the view provides no icon editing', () => {
    expect(mounted().querySelector('.icon-chip')).toBeNull()
  })

  it('tells the server the C4 type each entity is drawn as', () => {
    const icons = editing()
    mounted(icons)

    expect(icons.register).toHaveBeenCalledWith(
      { instance_id: SCOPE.artifact_id, entity_id: SCOPE.artifact_id, drawn_as: 'software-system' },
    )
    expect(icons.register).toHaveBeenCalledWith(
      { instance_id: API.artifact_id, entity_id: API.artifact_id, drawn_as: 'container' },
    )
  })

  it('names no C4 type for an entity no role takes', () => {
    const icons = editing()
    mounted(icons)

    expect(icons.register).toHaveBeenCalledWith({ instance_id: ODD.artifact_id, entity_id: ODD.artifact_id })
  })

  it('opens the picker under the row whose chip was pressed', async () => {
    const host = mounted(editing())
    const rows = [...host.querySelectorAll('.mbp-entity-row')]
    const apiRow = rows.find((row) => row.textContent?.includes('Orders API'))!

    apiRow.querySelector<HTMLButtonElement>('.icon-chip')!.click()
    await new Promise((resolve) => setTimeout(resolve))

    expect(apiRow.nextElementSibling?.matches('.mbp-entity-row')).toBe(false)
    expect(host.querySelectorAll('.icon-chip[aria-expanded="true"]')).toHaveLength(1)
  })
})
