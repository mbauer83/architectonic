import { computed, provide, type InjectionKey, type Ref } from 'vue'
import type { IconStyle, ShownIcon } from '../../domain/schemas/icons'
import type { ModelService } from '../../application/ModelService'
import {
  instanceIconOf, typeIconOf, withInstanceIcon, withLocalIcon, withTypeIcon,
  type IconScope, type IconStatement, type IconUploadForDiagram,
} from '../lib/diagramIcons'
import { useShownIcons } from './useShownIcons'

/** A row of the diagram editor as far as icons are concerned: the drawing, and the entity it draws. */
interface IconRow {
  readonly entity: { readonly artifact_id: string; readonly artifact_type: string }
  readonly occurrenceId?: string | null
}

/**
 * Everything a row needs to show and change its element's icon, provided by the editing view so the
 * row list takes it without every layer in between carrying it.
 */
export interface DiagramIconEditing {
  /** The styles this diagram type draws; empty when it draws no icons, and then no row offers any. */
  readonly styles: Ref<readonly IconStyle[]>
  readonly shownFor: (instanceId: string) => { readonly icon: ShownIcon; readonly picture: string } | undefined
  readonly statedAt: (instanceId: string, typeName: string) => Partial<Record<IconScope, IconStatement>>
  readonly choose: (instanceId: string, typeName: string, scope: IconScope, statement: IconStatement | null) => void
  readonly upload: (
    instanceId: string, typeName: string, scope: IconScope, upload: IconUploadForDiagram, style: IconStyle | undefined,
  ) => void
}

export const diagramIconsKey: InjectionKey<DiagramIconEditing> = Symbol('diagramIcons')

export const instanceIdOfRow = (row: IconRow): string => row.occurrenceId ?? row.entity.artifact_id

/**
 * The editor's icon state: which icon each row shows (asked of the server), and the statements a
 * choice in a row makes, written through the view's own `write` so they join its pending edits.
 */
export function useDiagramIcons(options: {
  svc: Pick<ModelService, 'previewShownIcons'>
  diagramEntities: Ref<Record<string, unknown>>
  write: (next: Record<string, unknown>) => void
  rows: Ref<readonly IconRow[]>
  styles: Ref<readonly IconStyle[]>
}): DiagramIconEditing {
  const { diagramEntities, write, styles } = options
  const instances = computed(() => options.rows.value.map((row) => ({
    instance_id: instanceIdOfRow(row), entity_id: row.entity.artifact_id,
  })))
  const enabled = computed(() => styles.value.length > 0)
  const { shown } = useShownIcons(options.svc, diagramEntities, instances, enabled)

  const stated = (data: Record<string, unknown>, instanceId: string, typeName: string, scope: IconScope,
    statement: IconStatement | null): Record<string, unknown> =>
    scope === 'instance' ? withInstanceIcon(data, instanceId, statement) : withTypeIcon(data, typeName, statement)

  const editing: DiagramIconEditing = {
    styles,
    shownFor: (instanceId) => {
      const icon = shown.value.icons[instanceId]
      const picture = icon ? shown.value.pictures[icon.picture] : undefined
      return icon && picture ? { icon, picture } : undefined
    },
    statedAt: (instanceId, typeName) => {
      const data = diagramEntities.value
      const instance = instanceIconOf(data, instanceId)
      const type = typeIconOf(data, typeName)
      return { ...(instance ? { instance } : {}), ...(type ? { type } : {}) }
    },
    choose: (instanceId, typeName, scope, statement) =>
      write(stated(diagramEntities.value, instanceId, typeName, scope, statement)),
    upload: (instanceId, typeName, scope, upload, style) => {
      const held = withLocalIcon(diagramEntities.value, upload)
      write(stated(held.diagramEntities, instanceId, typeName, scope, { icon: held.icon, ...(style ? { style } : {}) }))
    },
  }
  provide(diagramIconsKey, editing)
  return editing
}
