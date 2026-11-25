/**
 * How a relationship type is named to a reader: the name the picture draws it by, as the renderer's
 * `display_connection_label` writes it in a relation's stereotype — the meta-ontology's prefix dropped,
 * `archimate-serving` → `serving`. Every surface that names a type in words uses this, so a list, a menu
 * and the picture never call one relation two things.
 */
export function connectionTypeLabel(connectionType: string): string {
  return connectionType.replace(/^archimate-/, '')
}
