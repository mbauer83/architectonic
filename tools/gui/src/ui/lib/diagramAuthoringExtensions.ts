import type { Component } from 'vue'
import type { DiagramTypeUiConfig, EntityDisplayInfo } from '../../domain'

/**
 * Props contract that every kind UI slot component must satisfy.
 * Register slot components via registerExtension(key, component).
 * Keys come from diagram type config.yaml → ui.type_ui_slots.<slot_name>.
 */
export interface DiagramTypeUiSlotProps {
  uiConfig: DiagramTypeUiConfig
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
}

type DiagramAuthoringExtension = {
  component: Component
  managedOwnTypes: string[]
  config: Record<string, unknown>
}

const extensions = new Map<string, DiagramAuthoringExtension>()

export const registerExtension = (
  key: string,
  component: Component,
  options?: { managedOwnTypes?: string[]; config?: Record<string, unknown> },
) => {
  extensions.set(key, {
    component,
    managedOwnTypes: options?.managedOwnTypes ?? [],
    config: options?.config ?? {},
  })
}

export const lookupExtension = (key: string): Component | undefined => extensions.get(key)?.component
export const lookupExtensionManagedOwnTypes = (key: string): string[] => extensions.get(key)?.managedOwnTypes ?? []
export const lookupExtensionConfig = (key: string): Record<string, unknown> => extensions.get(key)?.config ?? {}
