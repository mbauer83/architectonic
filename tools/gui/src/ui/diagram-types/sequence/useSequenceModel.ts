import { computed } from 'vue'

export interface Lifeline {
  id: string
  label: string
  participant_type?: string
  entity_id?: string
}

export interface Message {
  id: string
  label?: string
  arrow?: 'sync' | 'async' | 'reply' | 'self' | 'create' | 'destroy'
  activate_target?: boolean
  deactivate_target?: boolean
}

export interface Operand {
  guard?: string
  start_message_id: string
  end_message_id: string
}

export interface Grouping {
  id: string
  kind: 'alt' | 'opt' | 'loop' | 'par' | 'break' | 'critical' | 'group'
  label?: string
  operands: Operand[]
}

export interface Note {
  id: string
  text: string
  placement?: 'left_of' | 'right_of' | 'over'
  lifeline_ids: string[]
  after_message_id?: string
}

interface Conn { id: string; conn_type: string; source: string; target: string }

function readList<T extends { id: string }>(data: Record<string, unknown>, key: string): T[] {
  const raw = data[key]
  return Array.isArray(raw) ? (raw as T[]).filter((x) => x && typeof x === 'object' && x.id) : []
}

function readConns(data: Record<string, unknown>): Conn[] {
  const c = data._connections
  return Array.isArray(c) ? (c as Conn[]) : []
}

function buildMaps(conns: Conn[]) {
  const from = new Map<string, string>()
  const to = new Map<string, string>()
  for (const c of conns) {
    if (c.conn_type === 'seq-from' && c.source && c.target) from.set(c.source, c.target)
    if (c.conn_type === 'seq-to' && c.source && c.target) to.set(c.source, c.target)
  }
  return { from, to }
}

export function useSequenceModel(
  getEntities: () => Record<string, unknown>,
  emit: (patch: Record<string, unknown>) => void,
) {
  const lifelines = computed(() => readList<Lifeline>(getEntities(), 'lifeline'))
  const messages = computed(() => readList<Message>(getEntities(), 'message'))
  const groupings = computed(() => readList<Grouping>(getEntities(), 'grouping'))
  const notes = computed(() => readList<Note>(getEntities(), 'note'))
  const connMaps = computed(() => buildMaps(readConns(getEntities())))
  const fromMap = computed(() => connMaps.value.from)
  const toMap = computed(() => connMaps.value.to)

  function save(
    lls: Lifeline[], msgs: Message[], grps: Grouping[], nts: Note[],
    fm: Map<string, string>, tm: Map<string, string>,
  ) {
    const existing = readConns(getEntities()).filter(
      (c) => c.conn_type !== 'seq-from' && c.conn_type !== 'seq-to',
    )
    let seq = Date.now()
    const mkId = () => `c-${(seq++).toString(36)}`
    const conns: Conn[] = [...existing]
    for (const [src, tgt] of fm) conns.push({ id: mkId(), conn_type: 'seq-from', source: src, target: tgt })
    for (const [src, tgt] of tm) conns.push({ id: mkId(), conn_type: 'seq-to', source: src, target: tgt })
    emit({ lifeline: lls, message: msgs, grouping: grps, note: nts, _connections: conns })
  }

  // ── Lifeline mutations ──────────────────────────────────────────────────────

  function addLifeline() {
    const id = `ll-${Date.now().toString(36)}`
    save(
      [...lifelines.value, { id, label: 'Participant', participant_type: 'participant' }],
      messages.value, groupings.value, notes.value, fromMap.value, toMap.value,
    )
  }

  function removeLifeline(id: string) {
    const newMsgs = messages.value.filter((m) => fromMap.value.get(m.id) !== id && toMap.value.get(m.id) !== id)
    const removedMsgIds = new Set(messages.value.filter((m) => fromMap.value.get(m.id) === id || toMap.value.get(m.id) === id).map((m) => m.id))
    const fm = new Map([...fromMap.value].filter(([k, v]) => v !== id && !removedMsgIds.has(k)))
    const tm = new Map([...toMap.value].filter(([k, v]) => v !== id && !removedMsgIds.has(k)))
    const newGrps = groupings.value.map((g) => ({
      ...g, operands: g.operands.filter((op) => !removedMsgIds.has(op.start_message_id) && !removedMsgIds.has(op.end_message_id)),
    })).filter((g) => g.operands.length > 0)
    const newNts = notes.value.map((n) => ({ ...n, lifeline_ids: n.lifeline_ids.filter((lid) => lid !== id) })).filter((n) => n.lifeline_ids.length > 0)
    save(lifelines.value.filter((l) => l.id !== id), newMsgs, newGrps, newNts, fm, tm)
  }

  function updateLifeline(id: string, patch: Partial<Lifeline>) {
    save(lifelines.value.map((l) => l.id === id ? { ...l, ...patch } : l), messages.value, groupings.value, notes.value, fromMap.value, toMap.value)
  }

  function reorderLifelines(newOrder: Lifeline[]) {
    save(newOrder, messages.value, groupings.value, notes.value, fromMap.value, toMap.value)
  }

  // ── Message mutations ───────────────────────────────────────────────────────

  function addMessage() {
    const id = `msg-${Date.now().toString(36)}`
    save(lifelines.value, [...messages.value, { id, label: '', arrow: 'sync' }], groupings.value, notes.value, fromMap.value, toMap.value)
  }

  function removeMessage(id: string) {
    const fm = new Map(fromMap.value); fm.delete(id)
    const tm = new Map(toMap.value); tm.delete(id)
    const newGrps = groupings.value.map((g) => ({
      ...g, operands: g.operands.filter((op) => op.start_message_id !== id && op.end_message_id !== id),
    })).filter((g) => g.operands.length > 0)
    const newNts = notes.value.map((n) => n.after_message_id === id ? { ...n, after_message_id: undefined } : n)
    save(lifelines.value, messages.value.filter((m) => m.id !== id), newGrps, newNts, fm, tm)
  }

  function updateMessage(id: string, patch: Partial<Message>) {
    save(lifelines.value, messages.value.map((m) => m.id === id ? { ...m, ...patch } : m), groupings.value, notes.value, fromMap.value, toMap.value)
  }

  function setMessageFrom(msgId: string, lifelineId: string) {
    const fm = new Map(fromMap.value)
    lifelineId ? fm.set(msgId, lifelineId) : fm.delete(msgId)
    save(lifelines.value, messages.value, groupings.value, notes.value, fm, toMap.value)
  }

  function setMessageTo(msgId: string, lifelineId: string) {
    const tm = new Map(toMap.value)
    lifelineId ? tm.set(msgId, lifelineId) : tm.delete(msgId)
    save(lifelines.value, messages.value, groupings.value, notes.value, fromMap.value, tm)
  }

  function reorderMessages(newOrder: Message[]) {
    save(lifelines.value, newOrder, groupings.value, notes.value, fromMap.value, toMap.value)
  }

  // ── Grouping mutations ──────────────────────────────────────────────────────

  function addGrouping() {
    const id = `grp-${Date.now().toString(36)}`
    const first = messages.value[0]
    const last = messages.value[messages.value.length - 1]
    if (!first || !last) return
    const grp: Grouping = { id, kind: 'alt', operands: [{ start_message_id: first.id, end_message_id: last.id }] }
    save(lifelines.value, messages.value, [...groupings.value, grp], notes.value, fromMap.value, toMap.value)
  }

  function removeGrouping(id: string) {
    save(lifelines.value, messages.value, groupings.value.filter((g) => g.id !== id), notes.value, fromMap.value, toMap.value)
  }

  function updateGrouping(id: string, patch: Partial<Grouping>) {
    save(lifelines.value, messages.value, groupings.value.map((g) => g.id === id ? { ...g, ...patch } : g), notes.value, fromMap.value, toMap.value)
  }

  // ── Note mutations ──────────────────────────────────────────────────────────

  function addNote() {
    const id = `note-${Date.now().toString(36)}`
    const nt: Note = { id, text: '', placement: 'right_of', lifeline_ids: lifelines.value.length > 0 ? [lifelines.value[0].id] : [] }
    save(lifelines.value, messages.value, groupings.value, [...notes.value, nt], fromMap.value, toMap.value)
  }

  function removeNote(id: string) {
    save(lifelines.value, messages.value, groupings.value, notes.value.filter((n) => n.id !== id), fromMap.value, toMap.value)
  }

  function updateNote(id: string, patch: Partial<Note>) {
    save(lifelines.value, messages.value, groupings.value, notes.value.map((n) => n.id === id ? { ...n, ...patch } : n), fromMap.value, toMap.value)
  }

  return {
    lifelines, messages, groupings, notes, fromMap, toMap,
    addLifeline, removeLifeline, updateLifeline, reorderLifelines,
    addMessage, removeMessage, updateMessage, setMessageFrom, setMessageTo, reorderMessages,
    addGrouping, removeGrouping, updateGrouping,
    addNote, removeNote, updateNote,
  }
}
