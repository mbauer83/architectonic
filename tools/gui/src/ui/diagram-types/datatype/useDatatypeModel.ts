import { computed } from 'vue'

export type ClassifierKind = 'class' | 'datatype' | 'enumeration' | 'primitive'
export const CLASSIFIER_KINDS: ClassifierKind[] = ['class', 'datatype', 'enumeration', 'primitive']

export const DT_CONN_TYPES = ['dt-association', 'dt-aggregation', 'dt-composition', 'dt-generalization', 'dt-dependency'] as const
export type DtConnType = (typeof DT_CONN_TYPES)[number]

export type AttrTypeRef =
  | { kind: 'primitive'; name: string }
  | { kind: 'classifier'; id: string }

export interface Attribute {
  id: string
  name: string
  type?: AttrTypeRef
  multiplicity?: string
  optional?: boolean
  role?: string
  provenance?: string
}

export interface UniqueKey {
  name?: string
  attribute_ids: string[]
}

export interface Classifier {
  id: string
  classifier_kind: ClassifierKind
  label?: string
  entity_id?: string
  attributes?: Attribute[]
  literals?: string[]
  is_abstract?: boolean
  identity?: string[]
  unique_keys?: UniqueKey[]
  role?: string
  internal_consistency_criteria?: string[]
  external_consistency_criteria?: string[]
  tags?: string[]
  provenance?: string
  note?: string
}

export interface GeneralizationSet {
  id: string
  label?: string
  is_covering?: boolean
  is_disjoint?: boolean
  note?: string
}

export interface DtConn {
  id: string
  conn_type: DtConnType
  source: string
  target: string
  src_multiplicity?: string
  tgt_multiplicity?: string
  label?: string
  backing_conn_id?: string
  generalization_set?: string
  note?: string
}

function readClassifiers(data: Record<string, unknown>): Classifier[] {
  const raw = data['classifier']
  return Array.isArray(raw) ? (raw as Classifier[]).filter((x) => x && typeof x === 'object' && x.id) : []
}

function readGeneralizationSets(data: Record<string, unknown>): GeneralizationSet[] {
  const raw = data['generalization_set']
  return Array.isArray(raw) ? (raw as GeneralizationSet[]).filter((x) => x && typeof x === 'object' && x.id) : []
}

function readConnections(data: Record<string, unknown>): DtConn[] {
  const raw = data['_connections']
  if (!Array.isArray(raw)) return []
  return (raw as DtConn[]).filter((x) => x && typeof x === 'object' && x.id && (DT_CONN_TYPES as readonly string[]).includes(x.conn_type))
}

function mkId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function useDatatypeModel(
  getEntities: () => Record<string, unknown>,
  emit: (patch: Record<string, unknown>) => void,
) {
  const classifiers = computed(() => readClassifiers(getEntities()))
  const generalizationSets = computed(() => readGeneralizationSets(getEntities()))
  const connections = computed(() => readConnections(getEntities()))

  function save(cls: Classifier[], sets: GeneralizationSet[], conns: DtConn[]) {
    const other = (getEntities()['_connections'] as DtConn[] | undefined ?? [])
      .filter((c) => !(DT_CONN_TYPES as readonly string[]).includes(c.conn_type))
    emit({ classifier: cls, generalization_set: sets, _connections: [...other, ...conns] })
  }

  function addClassifier(
    id?: string,
    label = 'Classifier',
    selectedBy?: { classifierId: string; attrIndex: number },
  ) {
    const newId = id ?? mkId('cls')
    const existing = selectedBy
      ? classifiers.value.map((classifier) => classifier.id === selectedBy.classifierId
        ? {
            ...classifier,
            attributes: (classifier.attributes ?? []).map((attr, index) =>
              index === selectedBy.attrIndex
                ? { ...attr, type: { kind: 'classifier' as const, id: newId } }
                : attr),
          }
        : classifier)
      : classifiers.value
    save([...existing, {
      id: newId,
      classifier_kind: 'class',
      label,
    }], generalizationSets.value, connections.value)
  }

  function removeClassifier(id: string) {
    save(
      classifiers.value.filter((c) => c.id !== id),
      generalizationSets.value,
      connections.value.filter((e) => e.source !== id && e.target !== id),
    )
  }

  function updateClassifier(id: string, patch: Partial<Classifier>) {
    save(
      classifiers.value.map((c) => c.id === id ? { ...c, ...patch } : c),
      generalizationSets.value,
      connections.value,
    )
  }

  function addAttribute(classifierId: string) {
    const cls = classifiers.value.find((c) => c.id === classifierId)
    if (!cls) return
    updateClassifier(classifierId, {
      attributes: [...(cls.attributes ?? []), { id: mkId('attr'), name: 'attr' }],
    })
  }

  function removeAttribute(classifierId: string, attrIndex: number) {
    const cls = classifiers.value.find((c) => c.id === classifierId)
    if (!cls) return
    updateClassifier(classifierId, { attributes: (cls.attributes ?? []).filter((_, i) => i !== attrIndex) })
  }

  function updateAttribute(classifierId: string, attrIndex: number, patch: Partial<Attribute>) {
    const cls = classifiers.value.find((c) => c.id === classifierId)
    if (!cls) return
    updateClassifier(classifierId, {
      attributes: (cls.attributes ?? []).map((a, i) => i === attrIndex ? { ...a, ...patch } : a),
    })
  }

  function addLiteral(classifierId: string) {
    const cls = classifiers.value.find((c) => c.id === classifierId)
    if (!cls) return
    updateClassifier(classifierId, { literals: [...(cls.literals ?? []), 'VALUE'] })
  }

  function removeLiteral(classifierId: string, index: number) {
    const cls = classifiers.value.find((c) => c.id === classifierId)
    if (!cls) return
    updateClassifier(classifierId, { literals: (cls.literals ?? []).filter((_, i) => i !== index) })
  }

  function updateLiteral(classifierId: string, index: number, value: string) {
    const cls = classifiers.value.find((c) => c.id === classifierId)
    if (!cls) return
    updateClassifier(classifierId, { literals: (cls.literals ?? []).map((l, i) => i === index ? value : l) })
  }

  function addGeneralizationSet(id?: string, label = 'Generalization set') {
    save(classifiers.value, [...generalizationSets.value, {
      id: id ?? mkId('gset'), label, is_covering: true, is_disjoint: true,
    }], connections.value)
  }

  function removeGeneralizationSet(id: string) {
    save(
      classifiers.value,
      generalizationSets.value.filter((s) => s.id !== id),
      connections.value.map((c) => c.generalization_set === id ? { ...c, generalization_set: undefined } : c),
    )
  }

  function updateGeneralizationSet(id: string, patch: Partial<GeneralizationSet>) {
    save(
      classifiers.value,
      generalizationSets.value.map((s) => s.id === id ? { ...s, ...patch } : s),
      connections.value,
    )
  }

  function addConnection(sourceId: string, targetId: string) {
    save(classifiers.value, generalizationSets.value, [...connections.value, {
      id: mkId('e'), conn_type: 'dt-association', source: sourceId, target: targetId,
    }])
  }

  function removeConnection(id: string) {
    save(classifiers.value, generalizationSets.value, connections.value.filter((e) => e.id !== id))
  }

  function updateConnection(id: string, patch: Partial<DtConn>) {
    save(classifiers.value, generalizationSets.value, connections.value.map((e) => e.id === id ? { ...e, ...patch } : e))
  }

  return {
    classifiers, generalizationSets, connections,
    addClassifier, removeClassifier, updateClassifier,
    addAttribute, removeAttribute, updateAttribute,
    addLiteral, removeLiteral, updateLiteral,
    addGeneralizationSet, removeGeneralizationSet, updateGeneralizationSet,
    addConnection, removeConnection, updateConnection,
  }
}
