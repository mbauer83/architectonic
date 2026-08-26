/**
 * The activity editor's outline: the declared step graph as a tree the author types into, and back.
 *
 * **The root rule is the server's, restated.** Which step leads a diagram is one question, and the
 * renderer answers it in `src/diagram_types/activity/_step_graph.py::entry_step` with three tiers:
 * a step nothing flows into and no branch owns; failing that a step no branch enters; failing that
 * the first declared step. This had only the first tier, and the second and third exist precisely
 * for a graph that loops — where every step is reached from somewhere, so no step satisfies tier one.
 *
 * The consequence was not a cosmetic difference. A diagram whose steps all sit inside a retry loop
 * fell through to "the steps no branch owns", which for such a graph is *none of them*: the editor
 * showed an empty outline for a diagram the renderer draws in full, and saving that emptiness would
 * have written the steps away. Measured on a four-step retry loop before this was changed.
 *
 * Two implementations of one rule, in two languages that cannot call each other. They are held
 * together by `ROOT_SAMPLES` in the test beside this file and by
 * `tests/architecture/test_the_editor_and_the_renderer_agree_on_the_entry_step.py`, which runs the
 * same graphs through the server. That is the same device the style-token ramp uses, and for the same
 * reason: the way to hold two languages to one convention is to write down what it produces and check
 * both sides against it.
 */

/** Keys the outline adds for its own use, which must never reach the model.
 *
 * `returns_to` is the outline saying "this chain goes back up there" — a fact about the shape of a
 * tree that cannot draw a backward edge, not a property of the step. It becomes a `step-flow`
 * connection on the way out; writing it into `diagram-entities` as well would put a key there that
 * nothing reads and no schema declares.
 */
/** The marker type for a branch that rejoins a step the outline has already placed.
 *
 * Not a step kind the model knows — it never reaches `diagram-entities`, because the step it names is
 * written where the outline first placed it. It exists so the *edge* has something to be written from,
 * and so a reader of the outline can see that the branch goes somewhere rather than stopping.
 */
export const REJOIN = 'rejoin'

const OUTLINE_ONLY_KEYS = [
  'then_steps', 'else_steps', 'branches', 'steps', 'lane_id', 'note', '_sourceKey', 'returns_to',
]

export type Lane = { id: string; label: string }
export type Step = { type: string; id: string; [key: string]: unknown }
export type LocalConn = { id: string; conn_type: string; source: string; target: string }

/** The `diagram-entities` keys that carry a step, as the server's `STEP_KEYS` lists them. */
export const STEP_KEYS = ['action', 'decision', 'fork', 'partition'] as const
export type StepKey = (typeof STEP_KEYS)[number]

export function getConns(data: Record<string, unknown>): LocalConn[] {
  const c = data._connections
  return Array.isArray(c) ? (c as LocalConn[]) : []
}

function buildSingleTarget(kcs: LocalConn[], connType: string): Map<string, string> {
  const m = new Map<string, string>()
  for (const kc of kcs) if (kc.conn_type === connType && kc.source && kc.target) m.set(kc.source, kc.target)
  return m
}

function buildMultiTarget(kcs: LocalConn[], connType: string): Map<string, string[]> {
  const m = new Map<string, string[]>()
  for (const kc of kcs) {
    if (kc.conn_type === connType && kc.source && kc.target) {
      const list = m.get(kc.source) ?? []
      list.push(kc.target)
      m.set(kc.source, list)
    }
  }
  return m
}

export function flatToRich(data: Record<string, unknown>): { lanes: Lane[]; steps: Step[] } {
  const kcs = getConns(data)
  const stepById = new Map<string, Step>()
  for (const key of STEP_KEYS) {
    const arr = data[key]
    if (Array.isArray(arr))
      for (const item of arr)
        if (item && typeof item === 'object' && (item as Step).id)
          stepById.set((item as Step).id, { ...(item as Step), type: (item as Step).type || key })
  }

  const flowNext = buildSingleTarget(kcs, 'step-flow')
  const thenFirst = buildSingleTarget(kcs, 'step-then')
  const elseFirst = buildSingleTarget(kcs, 'step-else')
  const forkBranches = buildMultiTarget(kcs, 'step-fork-branch')
  const containsFirst = buildSingleTarget(kcs, 'step-contains')
  const laneIdx = buildSingleTarget(kcs, 'step-in-lane')
  const noteByStep = new Map<string, { side: string; text: string }>()
  const noteById = new Map<string, { side: string; text: string }>()
  const rawNotes = data.note
  if (Array.isArray(rawNotes))
    for (const n of rawNotes as Step[])
      if (n.id) noteById.set(String(n.id), {
        side: typeof n.side === 'string' ? n.side : 'right',
        text: typeof n.text === 'string' ? n.text : '',
      })
  for (const kc of kcs)
    if (kc.conn_type === 'step-note-of' && kc.source && kc.target && noteById.has(kc.source))
      noteByStep.set(kc.target, noteById.get(kc.source)!)

  const branchEntries = new Set<string>([
    ...thenFirst.values(), ...elseFirst.values(), ...containsFirst.values(),
    ...[...forkBranches.values()].flat(),
  ])
  const branchOwned = new Set(branchEntries)
  let changed = true
  while (changed) {
    changed = false
    for (const [src, tgt] of flowNext)
      if (branchOwned.has(src) && !branchOwned.has(tgt)) {
        branchOwned.add(tgt)
        changed = true
      }
  }

  // One visited set for the whole outline, not one per chain.
  //
  // A per-chain set stops a *straight* run from repeating, and does nothing about a returning flow:
  // walking a decision's else-arm starts a fresh chain, which walks back round to the decision, which
  // opens its arms again. That recursed until the stack gave out — the same shape as the renderer's
  // own loop emission, which is fixed the same way, by marking a step visited before descending into
  // what it contains rather than after.
  //
  // A step is therefore placed once, where the outline first reaches it. That is what the tree can
  // express: a returning flow is an edge, and an outline of nested lists has no way to draw an edge
  // back to a step already above it.
  const placed = new Set<string>()

  const enrich = (step: Step): Step => {
    const r: Step = { ...step }
    const laneId = laneIdx.get(step.id)
    if (laneId) r.lane_id = laneId
    const note = noteByStep.get(step.id)
    if (note) r.note = note
    if (step.type === 'decision') {
      r.then_steps = buildChain(thenFirst.get(step.id))
      r.else_steps = buildChain(elseFirst.get(step.id))
    }
    if (step.type === 'fork') r.branches = (forkBranches.get(step.id) ?? []).map(id => buildChain(id))
    if (step.type === 'partition') r.steps = buildChain(containsFirst.get(step.id))
    return r
  }

  const buildChain = (startId: string | undefined): Step[] => {
    // A branch whose first step is already in the outline *rejoins* it. Two of a diagram's branches
    // converging on one step is ordinary — the shipped scratchpad diagram does it — and a tree has
    // nowhere to put the second arrival. Recorded as a marker so the edge survives the write.
    //
    // Both ways of losing it have been measured on that diagram. Placing the step in both arms wrote
    // it into `diagram-entities` **twice** (fourteen placements for thirteen steps); placing it once
    // and saying nothing dropped one of its two entry edges. The marker is neither: the step is
    // written once, and both edges that reach it are written.
    if (startId && placed.has(startId)) {
      return [{ id: startId, type: REJOIN, label: stepById.get(startId)?.label ?? startId }]
    }
    const result: Step[] = []
    let id: string | undefined = startId
    while (id && !placed.has(id)) {
      const s = stepById.get(id)
      if (!s) break
      placed.add(id)
      result.push(enrich(s))
      id = flowNext.get(id)
    }
    // Where the chain stopped because the next step is already in the outline, the flow *returns*
    // there. Recorded on the last step rather than dropped: a nested list cannot draw an edge back
    // to something above it, so without this the arm that loops and the arm that simply ends look
    // identical — and which arm leaves the loop is the one thing an author needs to see. `undefined`
    // rather than absent-and-falsy so a step whose chain ran out naturally says nothing at all.
    if (id && placed.has(id) && result.length > 0) {
      result[result.length - 1] = { ...result[result.length - 1], returns_to: id }
    }
    return result
  }

  // Three tiers, the server's, in its order. Tiers two and three exist for a graph that loops:
  // every step of a cycle is reached from somewhere, so tier one finds nothing there, and an entry
  // into a cycle is a choice rather than a fact — any of them shows the whole loop.
  const hasIncomingFlow = new Set(flowNext.values())
  const ids = [...stepById.keys()]
  const root =
    ids.find(id => !branchOwned.has(id) && !hasIncomingFlow.has(id))
    ?? ids.find(id => !branchEntries.has(id))
    ?? ids[0]

  // The unowned-step fallback is kept for a graph with no steps at all, and for nothing else. It
  // used to run whenever tier one failed, which for a diagram that is entirely a loop means every
  // step is branch-owned and the outline came back empty — for a diagram the renderer draws in full.
  const topLevelSteps = root ? buildChain(root) : STEP_KEYS.flatMap(key => {
    const arr = data[key]
    return Array.isArray(arr)
      ? (arr as Step[])
        .filter(s => s?.id && !branchOwned.has(String(s.id)))
        .map(s => enrich({ ...s, type: s.type || key }))
      : []
  })

  const lanes = Array.isArray(data.swimlane)
    ? (data.swimlane as Lane[]).filter(l => l && l.id)
    : []
  return { lanes, steps: topLevelSteps }
}

export function richToFlat(lanes: Lane[], richSteps: Step[], existingConns: LocalConn[]): Record<string, unknown> {
  const entities: Record<string, Step[]> = {}
  const conns: LocalConn[] = []
  let seq = Date.now()
  const mkId = () => `c-${(seq++).toString(36)}`

  const addConn = (conn_type: string, source: string, target: string) =>
    conns.push({ id: mkId(), conn_type, source, target })

  const flattenStep = (step: Step) => {
    const key = (step.type as StepKey) || 'action'
    if (!entities[key]) entities[key] = []
    const flat: Step = { type: step.type, id: step.id }
    for (const [k, v] of Object.entries(step))
      if (!OUTLINE_ONLY_KEYS.includes(k)) flat[k] = v
    entities[key].push(flat)
    if (typeof step.lane_id === 'string' && step.lane_id) addConn('step-in-lane', step.id, step.lane_id)
    // The edge that closes a loop. A chain writes `step-flow` between consecutive steps, so an edge
    // back to a step *above* this one in the outline has no consecutive pair to be written from —
    // and was therefore dropped on every save. Opening a diagram with a retry loop and saving it
    // unchanged turned the loop into a straight chain, silently and with nothing to notice it.
    if (typeof step.returns_to === 'string' && step.returns_to)
      addConn('step-flow', step.id, step.returns_to)
    if (step.note && typeof step.note === 'object') {
      const n = step.note as { side?: string; text?: string }
      const noteId = `note-${step.id}`
      if (!entities.note) entities.note = []
      entities.note.push({ type: 'note', id: noteId, side: n.side ?? 'right', text: n.text ?? '' })
      addConn('step-note-of', noteId, step.id)
    }
    if (step.type === 'decision') {
      flattenBranch(step.id, 'step-then', (step.then_steps as Step[] | undefined) ?? [])
      flattenBranch(step.id, 'step-else', (step.else_steps as Step[] | undefined) ?? [])
    }
    if (step.type === 'fork') {
      for (const branch of (step.branches as Step[][] | undefined) ?? [])
        flattenBranch(step.id, 'step-fork-branch', branch)
    }
    if (step.type === 'partition')
      flattenBranch(step.id, 'step-contains', (step.steps as Step[] | undefined) ?? [])
  }

  const flattenBranch = (parentId: string, entryConnType: string, steps: Step[]) => {
    for (let i = 0; i < steps.length; i++) {
      const connType = i === 0 ? entryConnType : 'step-flow'
      const source = i === 0 ? parentId : steps[i - 1].id
      addConn(connType, source, steps[i].id)
      // A rejoin contributes its edge and nothing else: the step itself is written where the outline
      // placed it, and flattening it here would put a second copy in `diagram-entities`.
      if (steps[i].type !== REJOIN) flattenStep(steps[i])
    }
  }

  for (let i = 0; i < richSteps.length; i++) {
    if (i > 0) addConn('step-flow', richSteps[i - 1].id, richSteps[i].id)
    if (richSteps[i].type !== REJOIN) flattenStep(richSteps[i])
  }

  const structural = new Set([
    'step-in-lane', 'step-flow', 'step-then', 'step-else',
    'step-fork-branch', 'step-contains', 'step-note-of',
  ])
  for (const kc of existingConns)
    if (!structural.has(kc.conn_type)) conns.push(kc)

  return { swimlane: lanes, ...entities, _connections: conns }
}
