// Pure helpers for the model-this affordance — unit-testable without a DOM.

// ArchiMate types an unbound assurance node can be modelled as.
export const MODELABLE_ARCH_TYPES = [
  'application-component',
  'application-collaboration',
  'application-service',
  'node',
  'system-software',
  'grouping',
] as const
export type ModelableArchType = (typeof MODELABLE_ARCH_TYPES)[number]

/** Only unbound-pending control-structure nodes carry the W501 modelling gap. */
export function isUnboundControlNode(nodeType?: string, bindingStatus?: string): boolean {
  return nodeType === 'control-structure-node' && bindingStatus === 'unbound-pending'
}

/** Derive the ArchiMate layer/domain for an arch type (keeps type↔domain consistent). */
export function domainForArchType(archType: string): string {
  if (archType === 'node' || archType === 'system-software') return 'technology'
  return 'application'
}

export interface ModelThisForm {
  archType: string
  name: string
  separationOfDuties: boolean
}

export function emptyModelThisForm(suggestedName: string): ModelThisForm {
  return { archType: 'application-component', name: suggestedName, separationOfDuties: false }
}

export function modelThisBody(nodeId: string, form: ModelThisForm): Record<string, unknown> {
  return {
    assurance_node_id: nodeId,
    suggested_arch_type: form.archType,
    suggested_name: form.name.trim(),
    domain: domainForArchType(form.archType),
    separation_of_duties: form.separationOfDuties,
  }
}

export interface BindOutcome {
  kind: 'bound' | 'task' | 'error'
  archId?: string
  message: string
}

/** Map the model-this HTTP response to a typed outcome for the panel. */
export function parseBindOutcome(status: number, body: Record<string, unknown>): BindOutcome {
  if (status === 423) return { kind: 'error', message: 'The assurance store is locked.' }
  if (status === 404) return { kind: 'error', message: 'Node not found.' }
  if (status < 200 || status >= 300) {
    const msg = typeof body['message'] === 'string' ? body['message'] : `HTTP ${status}`
    return { kind: 'error', message: msg }
  }
  if (body['outcome'] === 'bound') {
    const archId = typeof body['arch_artifact_id'] === 'string' ? body['arch_artifact_id'] : ''
    return { kind: 'bound', archId, message: `Bound to ${archId}.` }
  }
  if (body['outcome'] === 'task_required') {
    return {
      kind: 'task',
      message: 'Architecture-write access required — a binding task was created for an '
        + 'architecture-write session (separation of duties).',
    }
  }
  return { kind: 'error', message: 'Unexpected response.' }
}
