import { computed, reactive, ref, watch, type InjectionKey, type Ref } from 'vue'
import {
  GRC_STEPS, ACCOUNTABLE_REF_TYPE,
  parseAttributes, summariseGrcComplete, grcStepBadges, gapNodeIds, unlinkedSources, linkedSourceIds,
  type AssuranceNode, type AssuranceEdge, type GrcStep, type GrcCompleteResponse,
} from '../views/AssuranceGrcWizard.helpers'

/**
 * Owns the GRC wizard's REST data layer: nodes/edges/guidance/completeness, every
 * create/patch/link mutation, and the derived per-step views (risks/controls/obligations,
 * gap sets, treated-by/complies-with lookups). Returned as one `reactive()` bundle,
 * provided/injected rather than passed as a prop, since every step component both reads and
 * triggers mutations on this one shared state (a prop can't legitimately be mutated,
 * `vue/no-mutating-props`).
 */
export function useGrcWizardData(analysisId: Ref<string | null>, stepKey: Ref<string>) {
  const currentStep = computed<GrcStep>(() => GRC_STEPS.find((s) => s.key === stepKey.value) ?? GRC_STEPS[0])

  const nodes = ref<AssuranceNode[]>([])
  const edges = ref<AssuranceEdge[]>([])
  const guidance = ref<{ what?: string; why?: string; how?: string }>({})
  const completeness = ref<GrcCompleteResponse | null>(null)
  const error = ref<string | null>(null)
  const busy = ref(false)

  const risks = computed(() => nodes.value.filter((n) => n.node_type === 'risk'))
  const controls = computed(() => nodes.value.filter((n) => n.node_type === 'assurance-constraint'))
  const obligations = computed(() => nodes.value.filter((n) => n.node_type === 'obligation'))
  const contentSteps = computed(() => grcStepBadges(nodes.value))

  const treatmentGapIds = computed(() => gapNodeIds(completeness.value, 'risk_has_treatment'))
  const ownerGapIds = computed(() => gapNodeIds(completeness.value, 'risk_has_owner'))
  const completenessSummary = computed(() => completeness.value ? summariseGrcComplete(completeness.value) : null)

  const hasOwner = (risk: AssuranceNode): boolean => !ownerGapIds.value.has(risk.node_id)

  const loadNodes = async (): Promise<void> => {
    if (!analysisId.value) { nodes.value = []; edges.value = []; return }
    const aid = encodeURIComponent(analysisId.value)
    const [nResp, eResp] = await Promise.all([
      fetch(`/api/assurance/nodes?analysis_id=${aid}`),
      fetch('/api/assurance/edges'),
    ])
    if (nResp.status === 423) { error.value = 'The assurance store is locked.'; return }
    const nBody = await nResp.json() as { nodes: AssuranceNode[] }
    nodes.value = nBody.nodes
    const ids = new Set(nodes.value.map((n) => n.node_id))
    const eBody = await eResp.json() as { edges: AssuranceEdge[] }
    edges.value = eBody.edges.filter((e) => ids.has(e.source_id) && ids.has(e.target_id))
  }

  const loadGuidance = async (): Promise<void> => {
    guidance.value = {}
    if (!currentStep.value.guidanceTopic) return
    const resp = await fetch(`/api/assurance/guidance?topic=${currentStep.value.guidanceTopic}`)
    if (resp.ok) guidance.value = await resp.json() as { what?: string; why?: string; how?: string }
  }

  const loadCompleteness = async (): Promise<void> => {
    if (!analysisId.value) return
    const resp = await fetch(`/api/assurance/grc-complete?analysis_id=${encodeURIComponent(analysisId.value)}`)
    if (resp.ok) completeness.value = await resp.json() as GrcCompleteResponse
  }

  const createNode = async (
    nodeType: string,
    name: string,
    attributes: Record<string, string> = {},
  ): Promise<string | null> => {
    if (!name.trim() || !analysisId.value) return null
    busy.value = true
    error.value = null
    try {
      const resp = await fetch('/api/assurance/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_type: nodeType, name: name.trim(), analysis_id: analysisId.value, attributes,
        }),
      })
      const body = await resp.json().catch(() => ({})) as Record<string, unknown>
      if (!resp.ok || typeof body['node_id'] !== 'string') {
        error.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
        return null
      }
      return body['node_id']
    } catch (e) {
      error.value = String(e)
      return null
    } finally {
      busy.value = false
    }
  }

  const createEdge = async (source: string, target: string, connType: string): Promise<void> => {
    await fetch('/api/assurance/edges', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_id: source, target_id: target, conn_type: connType }),
    })
  }

  // Assurance edits replace attributes wholesale, so merge before PATCH.
  const patchAttributes = async (risk: AssuranceNode, changes: Record<string, string>): Promise<void> => {
    busy.value = true
    try {
      await fetch(`/api/assurance/nodes/${encodeURIComponent(risk.node_id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ attributes: { ...parseAttributes(risk), ...changes } }),
      })
      await loadNodes()
      await loadCompleteness()
    } finally {
      busy.value = false
    }
  }

  const setTreatment = (risk: AssuranceNode, treatment: string): void => {
    if (treatment) void patchAttributes(risk, { treatment })
  }

  const ownerInput = ref<Record<string, string>>({})

  const assignOwner = async (risk: AssuranceNode): Promise<void> => {
    const archId = (ownerInput.value[risk.node_id] ?? '').trim()
    if (!archId) return
    busy.value = true
    error.value = null
    try {
      const resp = await fetch('/api/assurance/arch-refs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assurance_node_id: risk.node_id, arch_artifact_id: archId, ref_type: ACCOUNTABLE_REF_TYPE,
        }),
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({})) as Record<string, unknown>
        error.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
        return
      }
      ownerInput.value[risk.node_id] = ''
      await loadCompleteness()
    } finally {
      busy.value = false
    }
  }

  const linkSource = async (sourceId: string, targetId: string, connType: string): Promise<void> => {
    busy.value = true
    try {
      await createEdge(sourceId, targetId, connType)
      await loadNodes()
    } finally {
      busy.value = false
    }
  }

  const treatedByRisks = (control: AssuranceNode): AssuranceNode[] => {
    const linked = linkedSourceIds(edges.value, control.node_id, 'treated-by')
    return risks.value.filter((r) => linked.has(r.node_id))
  }

  const compliantControls = (obligation: AssuranceNode): AssuranceNode[] => {
    const linked = linkedSourceIds(edges.value, obligation.node_id, 'complies-with')
    return controls.value.filter((c) => linked.has(c.node_id))
  }

  const unlinkedRisksFor = (control: AssuranceNode) =>
    unlinkedSources(risks.value, edges.value, control.node_id, 'treated-by')
  const unlinkedControlsFor = (obligation: AssuranceNode) =>
    unlinkedSources(controls.value, edges.value, obligation.node_id, 'complies-with')

  const sealBaseline = async (): Promise<void> => {
    busy.value = true
    try {
      await fetch('/api/assurance/baselines/seal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: `GRC analysis ${analysisId.value}`, analysis_id: analysisId.value }),
      })
      await loadCompleteness()
    } finally {
      busy.value = false
    }
  }

  watch(analysisId, () => {
    void loadNodes()
    void loadCompleteness()
  })
  watch(stepKey, () => {
    void loadGuidance()
    if (stepKey.value === 'treatment' || stepKey.value === 'coverage') void loadCompleteness()
  })

  return reactive({
    currentStep, nodes, edges, guidance, completeness, error, busy,
    risks, controls, obligations, contentSteps, treatmentGapIds, ownerGapIds, completenessSummary,
    ownerInput,
    hasOwner, loadNodes, loadGuidance, loadCompleteness, createNode, patchAttributes, setTreatment,
    assignOwner, linkSource, treatedByRisks, compliantControls, unlinkedRisksFor, unlinkedControlsFor,
    sealBaseline,
  })
}

export type GrcWizardDataApi = ReturnType<typeof useGrcWizardData>

export const grcWizardDataKey: InjectionKey<GrcWizardDataApi> = Symbol('grcWizardData')
