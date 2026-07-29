/**
 * Pure logic helpers for AssuranceNodeForm.
 * Extracted so they can be unit-tested without mounting the component.
 */

export interface AssuranceNodeFormData {
  node_type: string
  name: string
  status: string
  tlp: string
  concern_class: string
  disposition: string
  uca_type: string
  binding_status: string
  node_role: string
  content_text: string
}

export function showConcernClass(nodeType: string): boolean {
  return ['assurance-constraint', 'risk', 'hazard', 'obligation'].includes(nodeType)
}

export function showDisposition(nodeType: string): boolean {
  return nodeType === 'assurance-constraint'
}

export function showUcaType(nodeType: string): boolean {
  return nodeType === 'unsafe-control-action'
}

export function showBindingStatus(nodeType: string): boolean {
  return nodeType === 'control-structure-node'
}

export function showNodeRole(nodeType: string): boolean {
  return nodeType === 'control-structure-node'
}

export function showSafeguardWarning(nodeType: string, disposition: string, concernClass: string): boolean {
  return (
    showDisposition(nodeType)
    && disposition === 'accepted'
    && ['safety', 'security'].includes(concernClass)
  )
}

export function canSubmit(nodeType: string, name: string, loading: boolean): boolean {
  return nodeType.trim() !== '' && name.trim() !== '' && !loading
}

export function resetTypeSpecificFields<T extends Partial<AssuranceNodeFormData>>(form: T): T {
  return { ...form, concern_class: '', disposition: '', uca_type: '', binding_status: '', node_role: '' }
}
