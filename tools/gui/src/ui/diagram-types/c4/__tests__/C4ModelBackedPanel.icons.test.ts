// @vitest-environment jsdom
//
// A derived entity shows the icon it shows on the diagram. Which C4 type it is drawn as is the server's
// answer, from the diagram type's projection, and a type-wide choice is stated under that type.

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

const editing = (drawn: Record<string, string> = {}): DiagramIconEditing => ({
  register: vi.fn<DiagramIconEditing['register']>(() => () => undefined),
  styles: ref(['badge', 'figure'] as const),
  shownFor: () => undefined,
  drawnAs: (id) => drawn[id],
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
      diagramOnlyTypes: [container()], diagramEntities: {},
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

  it('asks about each derived entity and the scope, naming no C4 type of its own', () => {
    const icons = editing()
    mounted(icons)

    for (const entity of [SCOPE, API, ODD]) {
      expect(icons.register).toHaveBeenCalledWith({ instance_id: entity.artifact_id, entity_id: entity.artifact_id })
    }
  })

  it('states a type-wide choice under the C4 type the server says the entity is drawn as', async () => {
    const icons = editing({ [API.artifact_id]: 'component' })
    const host = mounted(icons)
    const apiRow = [...host.querySelectorAll('.mbp-entity-row')].find((row) => row.textContent?.includes('Orders API'))!

    apiRow.querySelector<HTMLButtonElement>('.icon-chip')!.click()
    await new Promise((resolve) => setTimeout(resolve))

    expect(host.querySelector('.icon-picker')!.textContent).toContain('All component here')
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
