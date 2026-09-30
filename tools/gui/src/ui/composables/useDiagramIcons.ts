import { computed, provide, shallowReactive, type InjectionKey, type Ref } from 'vue'
import type { IconStyle, ShownIcon } from '../../domain/schemas/icons'
import type { ModelService } from '../../application/ModelService'
import type { EditedInstance } from '../../ports/IconRepository'
import {
  instanceIconOf, typeIconOf, withInstanceIcon, withLocalIcon, withTypeIcon,
  type IconScope, type IconStatement, type IconUploadForDiagram,
} from '../lib/diagramIcons'
import { useShownIcons } from './useShownIcons'

/**
 * Everything a row needs to show and change its element's icon, provided by the editing view so the
 * rows take it without every layer in between carrying it. Each row that shows an icon registers the
 * instance it shows, so the view never has to know which instances a notation draws: an ArchiMate
 * entity row, a C4 card and a C4 model-backed row all say so the same way.
 */
export interface DiagramIconEditing {
  /** Ask about *instance* for as long as its row is shown; the returned function stops asking. */
  readonly register: (instance: EditedInstance) => () => void
  /** The styles this diagram type draws; empty when it draws no icons, and then no row offers any. */
  readonly styles: Ref<readonly IconStyle[]>
  readonly shownFor: (instanceId: string) => { readonly icon: ShownIcon; readonly picture: string } | undefined
  /** The type the diagram draws the instance as, where the server's projection says (a C4 container). */
  readonly drawnAs: (instanceId: string) => string | undefined
  readonly statedAt: (instanceId: string, typeName: string) => Partial<Record<IconScope, IconStatement>>
  readonly choose: (instanceId: string, typeName: string, scope: IconScope, statement: IconStatement | null) => void
  readonly upload: (
    instanceId: string, typeName: string, scope: IconScope, upload: IconUploadForDiagram, style: IconStyle | undefined,
  ) => void
}

export const diagramIconsKey: InjectionKey<DiagramIconEditing> = Symbol('diagramIcons')

/**
 * The editor's icon state: which icon each row shows (asked of the server), and the statements a
 * choice in a row makes, written through the view's own `write` so they join its pending edits.
 */
export function useDiagramIcons(options: {
  svc: Pick<ModelService, 'previewShownIcons'>
  diagramType: Ref<string | undefined>
  diagramEntities: Ref<Record<string, unknown>>
  write: (next: Record<string, unknown>) => void
  styles: Ref<readonly IconStyle[]>
}): DiagramIconEditing {
  const { diagramEntities, write, styles } = options
  // A row may be shown twice (the same instance in two lists); it is asked about once, until both go.
  const registered = shallowReactive(new Map<string, { instance: EditedInstance; rows: number }>())
  const instances = computed(() => [...registered.values()].map((entry) => entry.instance))
  const register = (instance: EditedInstance): (() => void) => {
    const entry = registered.get(instance.instance_id)
    registered.set(instance.instance_id, { instance, rows: (entry?.rows ?? 0) + 1 })
    return () => {
      const current = registered.get(instance.instance_id)
      if (!current) return
      if (current.rows > 1) registered.set(instance.instance_id, { ...current, rows: current.rows - 1 })
      else registered.delete(instance.instance_id)
    }
  }
  const enabled = computed(() => styles.value.length > 0)
  const { shown } = useShownIcons(options.svc, options.diagramType, diagramEntities, instances, enabled)

  const stated = (data: Record<string, unknown>, instanceId: string, typeName: string, scope: IconScope,
    statement: IconStatement | null): Record<string, unknown> =>
    scope === 'instance' ? withInstanceIcon(data, instanceId, statement) : withTypeIcon(data, typeName, statement)

  const editing: DiagramIconEditing = {
    register,
    styles,
    shownFor: (instanceId) => {
      const icon = shown.value.icons[instanceId]
      const picture = icon ? shown.value.pictures[icon.picture] : undefined
      return icon && picture ? { icon, picture } : undefined
    },
    drawnAs: (instanceId) => shown.value.drawn_as[instanceId],
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
